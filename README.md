# mosaic
mosaic是一个合成马赛克图片([wiki](https://en.wikipedia.org/wiki/Photographic_mosaic),[中文百科](https://baike.baidu.com/item/%E9%A9%AC%E8%B5%9B%E5%85%8B%E6%8B%BC%E5%9B%BE/8933804?fr=aladdin))的工具

> 此项目fork自[codebox/mosaic](https://github.com/codebox/mosaic),原项目是基于python2.X，本项目将其升级到了python3.X。
组合图片的核心代码仍使用原项目代码，本项目修改了部分代码提供了定制化能力

## 基本命令

### 参数
```
-i [--image]     : 原图片地址
-t [--tiles_dir] : 素材目录地址
-o [--outfile]   : 输出文件地址 【可选 默认当前目录】
```

### 运行
```
> python3 -i "/home/Downloads/origin.jpg" -t "/home/Downloads/Pool"
```

### 运行效果
![原始图片](img/origin.jpg)

![合成后图片](img/mosaic.jpg)

![合成细节](img/detail.jpg)
