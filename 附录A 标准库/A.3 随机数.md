[总目录](<../目录.md>) · [本章目录](<01 章节导读.md>) · [上一篇](<../附录A 标准库/A.2 算法概览.md>) · [下一篇](<../索引与封底/索引.md>)

> 原 PDF 第 1270–1274 页。

<!-- PDF 第 1270 页 -->

# **A.3** 随机数

标准库定义了一组随机数引擎类和适配器,使用不同数学方法生成伪随机数。标准库还定义了一组分布模板,根据不同的概率分布生成随机数。引擎和分布类型的名字都与它们的数学性质相对应。

这些类如何生成随机数的细节已经大大超出了本书的范围。在本节中,我们将列出这些引擎和分布类型,但读者需要查询其他资料来学习如何使用这些类型。

# **A.3.1** 随机数分布

除了总是生成bool类型的bernoulli\_distribution外,其他分布类型都是模板。每个模板都接受单个类型参数,它指出了分布生成的结果类型。

分布类与我们已经用过的其他类模板不同,它们限制了我们可以为模板类型指定哪些类型。一些分布模板只能用来生成浮点数,而其他模板只能用来生成整数。

在下面的描述中,我们通过将类型说明为*template\_name*<RealT>来指出分布生成浮点数。对这些模板,我们可以用float、double或long double代替RealT。类似的,IntT表示要求一个内置整型类型,但不包括 bool类型或任何char类型。可以用来代替IntT的类型是short、int、long、 long long、unsigned short、unsigned int、unsigned long或unsigned long long。

分布模板定义了一个默认模板类型参数(参见17.4.2节,第664 页)。整型分布的默认参数是int,生成浮点数的模板的默认参数是 double。

每个分布的构造函数都有这种分布特定的参数。某些参数指出了分布的范围。这些范围与迭代器范围不同,都是包含的。

均匀分布

<!-- PDF 第 1271 页 -->

### **uniform\_int\_distribution<IntT>u(m,n);**

### **uniform\_real\_distribution<RealT>u(x,y);**

生成指定类型的,在给定包含范围内的值。m(或x)是可以返回的最小值;n(或y)是最大值。m默认为0;n默认为类型IntT对象可以表示的最大值。x默认为0.0,y默认为1.0。

伯努利分布

# **bernoulli\_distribution b(p);**

以给定概率p生成true;p的默认值为0.5。

# **binomial\_distribution<IntT>b(t,p);**

分布是按采样大小为整型值t,概率为p生成的;t的默认值为1,p的默认值为0.5。

## **geometric\_distribution<IntT>g(p);**

每次试验成功的概率为p;p的默认值为0.5。

### **negative\_binomial\_distribution<IntT>nb(k,p);**

k(整型值)次试验成功的概率为p;k的默认值为1,p的默认值为 0.5。

# 泊松分布

# **poisson\_distribution<IntT>p(x);**

均值为double值x的分布。

# **exponential\_distribution<RealT>e(lam);**

指数分布,参数lambda通过浮点值lam给出;lam的默认值为1.0。

# **gamma\_distribution<RealT>g(a,b);**

alpha(形状参数)为a,beta(尺度参数)为b;两者的默认值均为 1.0。

# **weibull\_distribution<RealT>w(a,b);**

形状参数为a,尺度参数为b的分布;两者的默认值均为1.0。

<!-- PDF 第 1272 页 -->

### **extreme\_value\_distribution<RealT>e(a,b);**

a的默认值为0.0,b的默认值为1.0。

正态分布

### **normal\_distribution<RealT>n(m,s);**

均值为m,标准差为s;m的默认值为0.0,s的默认值为1.0。

### **lognormal\_distribution<RealT>ln(m,s);**

均值为m,标准差为s;m的默认值为0.0,s的默认值为1.0。

### **chi\_squared\_distribution<RealT>c(x);**

自由度为x;默认值为1.0。

### **cauchy\_distribution<RealT>c(a,b);**

位置参数a和尺度参数b的默认值分别为0.0和1.0。

# **fisher\_f\_distribution<RealT>f(m,n);**

自由度为m和n;默认值均为1。

### **student\_t\_distribution<RealT>s(n);**

自由度为n;n的默认值均为1。

抽样分布

# **discrete\_distribution<IntT>d(i,j);**

# **discrete\_distribution<IntT>d{il};**

i和j是一个权重序列的输入迭代器,il是一个权重的花括号列表。权重必须能转换为double。

### **piecewise\_constant\_distribution<RealT>pc(b,e,w);**

b、e和w是输入迭代器。

## **piecewise\_linear\_distribution<RealT>pl(b,e,w);**

b、e和w是输入迭代器。

<!-- PDF 第 1273 页 -->

## **A.3.2** 随机数引擎

标准库定义了三个类,实现了不同的算法来生成随机数。标准库还定义了三个适配器,可以修改给定引擎生成的序列。引擎和引擎适配器类都是模板。与分布的参数不同,这些引擎的参数更为复杂,且需深入了解特定引擎使用的数学知识。我们在这里列出所有引擎,以便读者对它们有所了解,但介绍如何生成这些类型超出了本书的范围。

标准库还定义了几个从引擎和适配器类型构造的类型。 default\_random\_engine类型是一个参数化的引擎类型的类型别名,参数化所用的变量的目的是在通常情况下获得好的性能。标准库还定义了几个类,它们都是一个引擎或适配器的完全特例化版本。标准库定义的引擎和特例化版本如下:

### **default\_random\_engine**

某个其他引擎类型的类型别名,目的是用于大多数情况。

### **linear\_congruential\_engine**

minstd\_rand0的乘数为16807,模为2147483647,增量为0。

minstd\_rand的乘数为48271,模为2147483647,增量为0。

#### **mersenne\_twister\_engine**

mt19937为32位无符号梅森旋转生成器。

mt19937\_64为64位无符号梅森旋转生成器。

### **subtract\_with\_carry\_engine**

ranlux24\_base为32位无符号借位减法生成器。

ranlux48\_base为64位无符号借位减法生成器。

### **discard\_block\_engine**

引擎适配器,将其底层引擎的结果丢弃。用要使用的底层引擎、块大小和旧块大小来参数化。

ranlux24使用ranlux24\_base引擎,块大小为223,旧块大小为23。

<!-- PDF 第 1274 页 -->

ranlux48使用ranlux48\_base引擎,块大小为389,旧块大小为11。

### **independent\_bits\_engine**

引擎适配器,生成指定位数的随机数。用要使用的底层引擎、结果的位数以及保存生成的二进制位的无符号整型类型来参数化。指定的位数必须小于指定的无符号类型所能保存的位数。

### **shuffle\_order\_engine**

引擎适配器,返回的就是底层引擎生成的数,但返回的顺序不同。 用要使用的底层引擎和要混洗的元素数目来参数化。

knuth\_b使用minstd\_rand0和表大小256。


