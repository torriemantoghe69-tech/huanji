# 幻境壁纸馆

一个本地优先的 Windows 壁纸卡片管理器。

## 功能
- 导入单张图片或整个文件夹
- 自动生成壁纸卡片和缩略图
- 分类筛选、搜索、收藏
- 大图预览与全屏查看
- 一键设置 Windows 桌面壁纸
- 图片与数据库保存在本机用户目录

## 开发运行
```bash
python -m pip install -r requirements.txt
python main.py
```

## 构建 Windows EXE
项目提供 GitHub Actions 工作流：推送代码后，在 Actions 页面运行 **Build Windows EXE**，完成后下载构建产物。
