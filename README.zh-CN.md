[English](README.md) · [简体中文](README.zh-CN.md)

# LaTeX Codex Collab

在 Codex 侧栏编辑 LaTeX 与 Markdown，支持本地 PDF 编译、每人独立的协作邀请和中文阅读译文。这是基于 LaTeX Codex 的改造版本。

## 主要功能

- LaTeX/Markdown 编辑、自动保存、标准/Vim/Emacs、补全、公式预览和搜索替换。
- 本地 XeLaTeX/pdfLaTeX/BibTeX、编译日志、PDF 下载及 Windows 无窗口后台编译。
- PDF 章节/页码导航、选字/框选、缩放拖动与源码 ↔ PDF 双向定位。
- Markdown/Obsidian HTML 实时预览及表格、callout、公式、TikZ 的可选 PDF 转换。
- 始终可见的 AI 批注列表、批量发送、模型/思考等级及写作风格提示词。
- 源码与临时 LaTeX PDF 逐处 Keep/Undo，编辑器与 PDF 校对独立开关。
- 持久项目问答，以及可选的主对话/外部 TeX 修改校对。
- 每人独立邀请、作者颜色、在线状态、非重叠编辑合并及冲突草稿保护。
- 所有者逐人授权 Codex；编辑成员无需 AI 权限即可编译，只读成员仅查看。
- 不调用 AI 的文字/图片/表格讨论注释、回复、解决与重新打开。
- 项目文件浏览编辑、所有者上传/新建/重命名/删除、单文件/ZIP 下载及回收区。
- 多项目共用网关端口、本地私人管理入口、按项目邀请及自动 LAN/可用端口选择。
- 可选中文阅读栏、跟随滚动、段落增量缓存与中文副本下载。
- 源码/PDF 历史对比、作者归属、可选缓存 AI 摘要及版本恢复。
- 八种界面语言、14 种配色、本地截图生成主题与跨文稿偏好。

完整操作、权限边界、限制及尚未通过的检查见 [功能说明](docs/FEATURES.zh-CN.md)。

## 最短用法

1. 下载或克隆本仓库，在 Codex 中打开仓库文件夹。
2. 告诉 Codex：**“请按 AGENTS.md 安装 latex-codex。”**
3. 新开对话，告诉 Codex：**“用 latex-codex 打开 main.tex。”** 也支持 Markdown 笔记。

独立启动、协作及公网穿透见 [安装与启动指南](docs/INSTALL.zh-CN.md)。安装后的插件名称仍为 `latex-codex`。

协作面向可信合作者：网页接口限制项目文件范围，但本地 TeX 编译不是操作系统沙箱。安装、启动选项和维护说明见 [AGENTS.md](AGENTS.md)。

## 简短功能演示

以下 GIF 使用虚构文档和测试成员实录，附中英文字幕。AI 修改建议与中文翻译均为实际运行结果；每个操作步骤稍作停留，方便阅读。

<details><summary>实时预览与搜索</summary>

![实时预览与搜索](docs/media/collab-01-live-preview.gif)

</details>
<details><summary>协作成员与所有者分配 Codex 权限</summary>

![协作权限](docs/media/collab-02-collaboration.gif)

</details>
<details><summary>文字注释、回复与解决讨论</summary>

![共享注释](docs/media/collab-03-comments.gif)

</details>
<details><summary>浏览与新建项目文件</summary>

![项目文件](docs/media/collab-04-project-files.gif)

</details>
<details><summary>Markdown 本地编译 PDF</summary>

![本地 PDF](docs/media/collab-05-pdf.gif)

</details>
<details><summary>AI 批注、Send 与逐处 Keep/Undo</summary>

![AI 批注](docs/media/collab-06-ai-annotations.gif)

</details>
<details><summary>可选中文翻译与缓存复用</summary>

![中文翻译](docs/media/collab-07-translation.gif)

</details>
<details><summary>源码历史、作者与已保存的 AI 修改要求</summary>

![项目历史](docs/media/collab-08-history.gif)

</details>

## 来源与致谢

本插件是在 [Fr0zenWatter/codex-latex-editor](https://github.com/Fr0zenWatter/codex-latex-editor/tree/main) 基础上改造的衍生版本。感谢 **Fr0zenWatter** 及原项目贡献者提供基础实现，也感谢随插件分发的第三方库作者；原有资源许可证予以保留。本改造版不代表原作者官方发布或背书。
