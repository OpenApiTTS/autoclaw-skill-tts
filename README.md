# skill-openapi

语音开放接口（TTS / 声音克隆 / 音频降噪）的 Agent 技能包。

把这个目录交给支持技能（Skill）的 AI Agent，就能用自然语言完成「文本 → 音频文件」；
也可以脱离 Agent，直接当命令行工具用。

- **接口文档**：[`SKILL.md`](SKILL.md)（同时是给 Agent 读的说明书）
- **命令行封装**：[`scripts/tts.py`](scripts/tts.py)，仅依赖 Python 3 标准库，无需 `pip install`
- **语言/方言枚举**：[`target-speech-enum.csv`](target-speech-enum.csv)

## 目录结构

三个文件的相对位置不要改动——`SKILL.md` 按 `scripts/tts.py` 这一相对路径引用脚本。

```
skill-openapi/
├── SKILL.md
├── scripts/
│   └── tts.py
└── target-speech-enum.csv
```

## 环境要求

- Python 3.8+
- 一个可用的 API Key（请求头 `sign`），向平台申请

建议放在不含空格与非 ASCII 字符的路径下，可以省掉不少引号转义的麻烦。

## 快速开始

### 1. 配置 API Key

macOS / Linux：

```bash
export VOICE_API_KEY="<你的key>"
export VOICE_API_BASE="https://openapi.anyvoice.cn"   # 可选，默认即此值
```

Windows PowerShell（当前窗口有效）：

```powershell
$env:VOICE_API_KEY = "<你的key>"
```

Windows 永久写入用户环境变量：

```powershell
setx VOICE_API_KEY "<你的key>"
```

> `setx` 对**已经打开**的窗口和已经启动的程序不生效。设置后需要重开终端；
> 如果由 Agent 客户端派生子进程，还要重启该客户端——它在启动时就已读取环境变量。

验证：

```bash
echo $VOICE_API_KEY          # PowerShell: echo $env:VOICE_API_KEY
```

### 2. 先手动跑通

接入 Agent 之前，建议先在终端里验证一遍，便于区分是接口问题还是 Agent 问题。

```bash
python3 scripts/tts.py voices
```

期望输出音色列表：

```
共 3 个音色：
  abc123    音色A
  def456    音色B
```

再试合成：

```bash
python3 scripts/tts.py tts --text "今天天气不错" -o out.mp3
```

打印出 `out.mp3` 且可正常播放，说明链路已通。

### 3. 接入 Agent

**作为技能导入**：在客户端的技能/连接器面板中导入本目录，之后直接描述需求即可，例如：

> 把这段文案用四川话合成语音，存到桌面：巴适得很，安逸得板。

不同客户端的导入入口与目录规范各异，请以其自身文档为准。

**直接喂给对话**（无技能机制时的兜底做法）：把 `SKILL.md` 全文粘贴进对话，并补充运行环境信息：

> 以上是接口说明书。脚本位于 `<脚本绝对路径>`，API Key 已配置在环境变量 `VOICE_API_KEY`。
> 现在：把「今天天气不错」合成语音，保存为 `out.mp3`。

这种方式要求 Agent 具备本地命令执行能力；若它只输出命令而不执行，手动复制到终端运行即可。

## 命令速查

```bash
# 列出音色
python3 scripts/tts.py voices

# 合成（不指定音色则自动用列表第一个）
python3 scripts/tts.py tts --text "今天天气不错" -o out.mp3

# 指定音色
python3 scripts/tts.py tts --text "你好" --voice abc123 -o out.mp3

# 方言 / 多语言
python3 scripts/tts.py tts --text "巴适得很" --lang sichuan -o out.mp3

# 情绪控制（仅普通话/英语/日语/西语/阿语可用）
python3 scripts/tts.py tts --text "太好啦" --emotion happy=0.8 -o out.mp3

# 长文本从 stdin 读取
python3 scripts/tts.py tts --text - -o out.mp3 < article.txt

# 按 taskId 查询结果
python3 scripts/tts.py result <taskId>

# 音频降噪（3~60 秒）
python3 scripts/tts.py denoise --file noisy.wav -o clean.wav

# 上传参考音频，创建新音色
python3 scripts/tts.py upload-voice --file sample.wav --name "音色A"

# 查看全部参数
python3 scripts/tts.py tts --help
```

不传 `-o` 时只打印音频 URL，便于管道接后续处理。

## Windows 注意事项

- 命令用 `python`，不是 `python3`。直接敲 `python3` 会跳转到 Microsoft Store 的占位程序。
- 路径分隔符用反斜杠：`python scripts\tts.py voices`；含空格的路径需加引号。
- 安装 Python 时务必勾选 **Add python.exe to PATH**，否则命令无法识别。
- 中文长文本不建议用 `--text` 直接传参，改为从文件读取（记事本另存为时编码选 UTF-8）：

  ```powershell
  Get-Content -Encoding UTF8 article.txt | python scripts\tts.py tts --text - -o out.mp3
  ```

- 短文本仍出现乱码时，先执行 `chcp 65001` 切换到 UTF-8 代码页。

## 常见问题

| 现象 | 原因与处理 |
|---|---|
| `无法将"python"项识别为...` | Python 未安装，或安装时未勾选 Add to PATH，重装即可 |
| 弹出 Microsoft Store | 在 Windows 上应使用 `python` 而非 `python3` |
| `未设置环境变量 VOICE_API_KEY` | `setx` 后未重开终端 / 未重启 Agent 客户端 |
| `[code=7] sign无效` | Key 复制有误（首尾空格、字符缺失），或账号 API 权限未开通 / 会员已过期。后者需联系平台客服处理 |
| `[code=1001]` | 单次文本超出字数上限（默认 5000 字符），拆分后分段合成 |
| `暂不支持该语言` | `--lang` 的取值不在服务端枚举内。去掉 `--lang` 并改用 `--style 3`，由模型按文本自行判断 |
| 中文显示为问号或方块 | 见上方「Windows 注意事项」 |
| 合成长时间不返回 | 脚本最长等待 5 分钟，超时会打印 `taskId`。用 `result <taskId>` 单独查询，不要重复提交任务 |

## 安全提示

API Key 请通过环境变量注入，不要写入代码、文档或聊天记录；分发本技能包时 Key 应单独传递。
