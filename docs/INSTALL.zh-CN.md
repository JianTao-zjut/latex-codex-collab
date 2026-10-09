# 安装与启动

[English](INSTALL.md) · [返回首页](../README.zh-CN.md) · [完整功能](FEATURES.zh-CN.md)

## 准备环境

需要已登录的 Codex 桌面应用及 CLI、Python 3.10+。PDF 编译需要已有 TeX Live、MiKTeX 或 MacTeX，提供 `xelatex` 或 `pdflatex`，以及 `bibtex`、`synctex`。Markdown HTML 实时预览无需 TeX；Markdown PDF 需要 XeLaTeX。缺少工具或 TeX 包时请自行准备，本插件不自动安装 TeX 或修改全局设置。

前端资源已附带，使用者无需 npm、pip 或 Poppler。macOS 可使用 `/Library/TeX/texbin`；Windows/Linux 的文件选择器可选用 tkinter，缺少时仍可通过命令打开文件。

## 在 Codex 安装

1. 下载或克隆本仓库，在 Codex 中打开仓库文件夹。
2. 告诉 Codex：“请按 AGENTS.md 安装 latex-codex。”也可在仓库根目录手动执行：

   ```sh
   codex plugin marketplace add .
   codex plugin add latex-codex@latex-codex-shared
   ```

   Windows 中 CLI 不在 PATH 时，在 Codex 提供的终端执行：

   ```powershell
   & $env:CODEX_CLI_PATH plugin marketplace add .
   & $env:CODEX_CLI_PATH plugin add latex-codex@latex-codex-shared
   ```

3. 新开对话，告诉 Codex：“用 latex-codex 打开 /path/to/main.tex。”也可以提供 `.md` / `.markdown` 路径。

保留仓库目录，作为本地插件源。升级时更新仓库后重新执行插件安装命令，在没有草稿、批注或运行任务时重启服务。

## 不通过对话启动

在仓库根目录运行并打开打印的 URL。macOS/Linux 通常使用 `python3`。

```sh
python plugins/latex-codex/scripts/editor.py /path/to/main.tex
```

默认只允许本机访问，自动选择可用端口。打开 Markdown 的方式相同。

## 协作与自动选择局域网地址

```sh
python plugins/latex-codex/scripts/editor.py /path/to/main.tex --collaborate --owner-name Owner --host auto --port auto
```

使用终端打印的私人所有者链接登录，在“协作”中生成每位伙伴自己的邀请，自行发送给对应的人。不要分享所有者或主管理员链接。Codex 权限需要所有者另外逐人授予；普通编辑、评论及编辑成员编译不依赖 Codex 权限。

`--host auto` 选择本机私有 IPv4，多个网卡/VPN 时可改为明确 IP。`--port auto` 先尝试 8765，占用时由系统分配空闲端口；需要固定入口时指定数字，例如 `--port 8765`，占用时明确报错，不偷偷换端口。

## 多项目共用端口

```sh
python plugins/latex-codex/scripts/gateway.py --project /path/to/paper/main.tex --project /path/to/notes/draft.md --host auto --port 8765 --owner-name Owner
```

私人本地管理链接用于选择或添加项目。协作者邀请自带项目路径，自动进入对应项目。项目注册记录在用户目录的 `.latex-codex/projects.json`，不应上传 Git。重启后管理会话重新登录，协作者的持久邀请和权限保留。

## 公网穿透

在已有协作/网关命令末尾添加实际公网入口，例如：

```sh
--public-url https://editor.example.com
```

将穿透的目标端口配置为实际监听端口，保留浏览器 Host，使用有效 HTTPS 证书。HTTP 与 HTTPS 入口不同，必须准确配置。插件不会安装穿透工具、开放防火墙或自动推断公网域名。多个入口可重复传入 `--public-url`。

项目根目录默认是主文件所在目录；多个子目录可使用 `--project-root /path/to/project`。选择专用文稿目录，普通项目文件和历史对协作者可见。可编辑成员的本地 TeX 编译没有 OS 沙箱，不适合将不可信陌生人作为编辑成员。

## 数据、迁移与发布

历史、注释、授权、回收区和翻译缓存保存在项目私有 `.latex-codex/`，偏好保存在用户目录；迁移文稿时一起备份项目私有数据，不要发布到 GitHub。运行服务期间保留未保存草稿，切换或升级前处理待发送批注和建议。

发布源码可使用白名单打包：

```sh
python plugins/latex-codex/scripts/package_source.py --output /path/to/latex-codex-source.zip
```

源码包排除文稿、PDF、数据库、缓存、凭据及演示媒体。完整选项、维护流程与检查结果见 [AGENTS.md](../AGENTS.md) 和 [功能说明](FEATURES.zh-CN.md)。

## 来源与致谢

本插件基于 [Fr0zenWatter/codex-latex-editor](https://github.com/Fr0zenWatter/codex-latex-editor/tree/main) 改造。感谢 **Fr0zenWatter** 及原项目贡献者；本仓库是衍生改造版，不代表原作者官方发布。
