"""Marker PDF conversion with explicit preservation of embedded raster content.

Marker's disable_ocr mode drops raster code classified as Code/Text.  Add those
PDF image objects as Picture blocks before Marker runs its standard processors.
All text extraction, layout, reading structure, and Markdown rendering use Marker.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import re
import time

os.environ.setdefault("MODEL_CACHE_DIR", "D:/DevCache/marker/models")
os.environ.setdefault("HF_HOME", "D:/DevCache/marker/huggingface")
os.environ.setdefault("TORCH_DEVICE", "cpu")
os.environ.setdefault("FAST_LAYOUT_NUM_THREADS", "4")
os.environ.setdefault("FAST_LAYOUT_SERVER_MAX_BATCH", "2")
os.environ.setdefault("SURYA_INFERENCE_BACKEND", "llamacpp")
os.environ.setdefault("OUTPUT_IMAGE_FORMAT", "PNG")
os.environ.setdefault("OMP_NUM_THREADS", "4")

import pypdfium2 as pdfium
from marker.builders.document import DocumentBuilder
from marker.builders.line import LineBuilder
from marker.builders.ocr import OcrBuilder
from marker.builders.structure import StructureBuilder
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict, shutdown_models
from marker.providers.registry import provider_from_filepath
from marker.schema import BlockTypes
from marker.schema.blocks import Picture
from marker.schema.polygon import PolygonBox


IMAGE_TYPES = (BlockTypes.Picture, BlockTypes.Figure, BlockTypes.Diagram)


class ImagePreservingConverter(PdfConverter):
    image_audit: list[dict]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.image_audit = []

    def preserve_images(self, document, filepath):
        with pdfium.PdfDocument(filepath) as source:
            for page in document.pages:
                source_page = source[page.page_id]
                height = source_page.get_height()
                boxes = []
                for obj in source_page.get_objects(max_depth=15):
                    if obj.type != pdfium.raw.FPDF_PAGEOBJ_IMAGE:
                        continue
                    left, bottom, right, top = obj.get_bounds()
                    box = PolygonBox.from_bbox([left, height-top, right, height-bottom])
                    box = box.fit_to_bounds(page.polygon.bbox)
                    if box.area > 0:
                        boxes.append(box)
                source_page.close()

                # Remove detector image fragments that lie inside an actual PDF
                # image (including the fragmented cover and the back cover).
                original_blocks = list(page.structure_blocks(document))
                for block in original_blocks:
                    if block.block_type in IMAGE_TYPES and any(
                        block.polygon.intersection_pct(box) > 0.98
                        for box in boxes
                    ):
                        page.remove_structure_items([block.id])
                        block.removed = True
                    elif not block.raw_text(document).strip() and any(
                        block.polygon.intersection_pct(box) > 0.5
                        or box.intersection_pct(block.polygon) > 0.5
                        for box in boxes
                    ):
                        # Empty code/equation regions otherwise render as nothing.
                        page.remove_structure_items([block.id])
                        block.removed = True

                added = 0
                covered = 0
                required_images = []
                for box in sorted(boxes, key=lambda b: (b.y_start, b.x_start)):
                    containers = [b for b in page.structure_blocks(document)
                                  if b.block_type in IMAGE_TYPES]
                    if any(box.intersection_pct(b.polygon) > 0.98 for b in containers):
                        covered += 1
                        continue
                    block = page.add_block(Picture, box)
                    block.source = "heuristics"
                    page.add_structure(block)
                    required_images.append(f"{block.id.to_path()}.png")
                    added += 1

                # This book is a single-column reflowed PDF.  Sorting at this
                # stage lets Marker's normal group builders see the raster code
                # at its original place between text paragraphs.
                if boxes:
                    page.structure.sort(key=lambda bid: (
                        document.get_block(bid).polygon.y_start,
                        document.get_block(bid).polygon.x_start,
                    ))
                self.image_audit.append({"page_id": page.page_id,
                                         "embedded_images": len(boxes),
                                         "added_pictures": added,
                                         "covered_by_picture": covered,
                                         "required_images": required_images})

    def build_document(self, filepath):
        provider = provider_from_filepath(filepath)(filepath, self.config)
        document = DocumentBuilder(self.config)(
            provider,
            self.resolve_dependencies(self.layout_builder_class),
            self.resolve_dependencies(LineBuilder),
            self.resolve_dependencies(OcrBuilder),
        )
        self.preserve_images(document, filepath)
        self.resolve_dependencies(StructureBuilder)(document)
        for processor in self.processor_list:
            processor(document)
        return document


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("--pages", help="Zero-based comma-separated sample pages")
    parser.add_argument("--batch-size", type=int, default=24)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    image_dir = args.work / "images"
    image_dir.mkdir(exist_ok=True)
    with pdfium.PdfDocument(str(args.pdf)) as pdf:
        total = len(pdf)
    pages = [int(x) for x in args.pages.split(",")] if args.pages else list(range(total))
    models = create_model_dict()
    start = time.monotonic()
    try:
        for offset in range(0, len(pages), args.batch_size):
            batch = pages[offset:offset+args.batch_size]
            stem = f"pages-{batch[0]+1:04d}-{batch[-1]+1:04d}"
            md_path = args.work / f"{stem}.md"
            meta_path = args.work / f"{stem}.json"
            if md_path.exists() and meta_path.exists():
                print(f"SKIP {stem}", flush=True)
                continue
            config = {"mode": "fast", "disable_ocr": True,
                      "page_range": batch, "paginate_output": True,
                      "pdftext_workers": 1, "disable_tqdm": True,
                      "highres_image_dpi": 240,
                      "keep_pageheader_in_output": True,
                      "keep_pagefooter_in_output": True,
                      "common_element_threshold": 2.0,
                      "max_streak": 100000,
                      "filter_blank_pages": False}
            converter = ImagePreservingConverter(artifact_dict=models, config=config)
            then = time.monotonic()
            rendered = converter(str(args.pdf))
            required = {name for row in converter.image_audit for name in row["required_images"]}
            missing_images = required - set(rendered.images)
            if missing_images:
                raise RuntimeError(f"Marker dropped required images: {sorted(missing_images)}")
            for name, img in rendered.images.items():
                img.save(image_dir / name, format="PNG", optimize=False)
            text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",
                          r"![\1](images/\2)", rendered.markdown)
            md_path.write_text(text, encoding="utf-8")
            meta = {"pages": batch, "marker_metadata": rendered.metadata,
                    "image_audit": converter.image_audit,
                    "output_images": list(rendered.images),
                    "seconds": round(time.monotonic()-then, 2)}
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            (args.work / "progress.json").write_text(json.dumps({
                "completed_pages": offset+len(batch), "total_pages": len(pages),
                "last_batch": stem, "elapsed_seconds": round(time.monotonic()-start),
            }, indent=2), encoding="utf-8")
            print(f"DONE {stem}: {len(batch)} pages, {len(rendered.images)} images, "
                  f"{meta['seconds']}s; {offset+len(batch)}/{len(pages)} pages; "
                  f"elapsed={time.monotonic()-start:.0f}s", flush=True)
            del rendered, converter
            gc.collect()
    finally:
        shutdown_models(models)


if __name__ == "__main__":
    run()
