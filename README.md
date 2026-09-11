# 在 AutoClaw（Windows）里使用语音开放接口

面向的是：把 `skill-openapi` 交给 AutoClaw，让它自己完成"文本 → 音频文件"。

需要准备三样东西：

1. `skill-openapi` 目录（SKILL.md + scripts/tts.py + target-speech-enum.csv）
2. 一个可用的 API Key（sign）
3. Windows 上的 Python 3

---

## 第一步：装 Python 3

AutoClaw 自己不带 Python，脚本跑不起来的话多半卡在这。

1. 打开 <https://www.python.org/downloads/windows/>，下载 Python 3.10 以上的安装包。
2. **安装第一屏务必勾选 `Add python.exe to PATH`**，否则后面命令找不到。
3. 装完开一个新的 PowerShell（开始菜单搜 "PowerShell"），验证：

```powershell
python --version
```

看到 `Python 3.x.x` 即可。

> **Windows 用 `python`，不是 `python3`。**
> SKILL.md 里的示例写的是 `python3 scripts/tts.py ...`，在 Windows 上要改成 `python scripts\tts.py ...`。
> 直接敲 `python3` 会弹出微软商店，那是 Windows 的占位程序，不是真的 Python。

脚本只用标准库，**不需要 pip install 任何东西**。

---

## 第二步：放好文件

建议放在一个没有中文、没有空格的路径，省得后面引号出问题：

```
C:\voice-skill\
    SKILL.md
    scripts\tts.py
    target-speech-enum.csv
```

**三个文件的相对位置不能变**。SKILL.md 里是按 `scripts/tts.py` 这个相对路径引用脚本的，
如果全都平铺在同一层，AI 会照着说明书去找 `scripts\tts.py` 然后报"文件不存在"。

---

## 第三步：设置 API Key

在 PowerShell 里执行（把 `你的key` 换成实际值）：

```powershell
setx VOICE_API_KEY "你的key"
```

`setx` 是**永久写入**用户环境变量，但**对已经开着的窗口不生效**。
设完必须：关掉所有 PowerShell 窗口重开，并且**重启 AutoClaw**——
AutoClaw 启动时就读好了环境变量，不重启它派生出来的 Python 进程照样读不到。

验证（新窗口里）：

```powershell
echo $env:VOICE_API_KEY
```

能打印出 key 就对了。

> 如果只想临时试一下、不写进系统，用这个（只在当前窗口有效）：
> ```powershell
> $env:VOICE_API_KEY = "你的key"
> ```

---

## 第四步：先手动验证一遍

**别急着交给 AI。** 先自己在 PowerShell 里跑通，否则出了问题分不清是接口的锅还是 AI 的锅。

```powershell
cd C:\voice-skill
python scripts\tts.py voices
```

期望输出是音色列表：

```
共 3 个音色：
  abc123    小王
  def456    客服女声
```

如果这一步就报错，对照下面的「排错」，**先解决掉再往下走**。

跑通了再试合成：

```powershell
python scripts\tts.py tts --text "今天天气不错" -o out.mp3
```

打印出 `out.mp3` 且文件能播放，说明整条链路是通的。

---

## 第五步：接入 AutoClaw

AutoClaw 左侧栏有 `Skill & 连接器`，输入框提示 `输入"@"使用技能`——技能从这里进。

> 我没有 AutoClaw 的技能目录规范，下面是通用做法。
> 具体导入入口以 `Skill & 连接器` 面板里的说明为准，如果它要求特定的目录结构或 manifest 格式，以它的为准。

**方式 A：作为技能导入**

打开 `Skill & 連接器` → 找到导入/添加技能 → 指向 `C:\voice-skill` 目录。
导入后在对话框里打 `@` 应该能看到这个技能，选中后直接说需求即可：

> 把这段文案用四川话合成语音，存到桌面：巴适得很，安逸得板。

**方式 B：直接喂给对话（最省事，先跑通用这个）**

新建一个对话，把 `SKILL.md` 的全文粘进去，然后补一句：

> 以上是接口说明书。脚本在 `C:\voice-skill\scripts\tts.py`，
> API Key 已设在环境变量 `VOICE_API_KEY`。
> Windows 环境，用 `python` 不是 `python3`。
> 现在：把「今天天气不错」合成语音，存到 `C:\voice-skill\out.mp3`。

方式 B 的前提是 AutoClaw 有执行命令的能力（截图显示 `Agent 在本地运行`，通常是有的）。
如果它只会把命令打印给你、不会自己执行，那就手动复制到 PowerShell 里跑。

---

## 中文文本的坑

Windows 命令行对中文参数不太友好，长文本尤其容易乱码。**超过一两句话就别用 `--text` 传了**，改成从文件读：

1. 用记事本写好文案，**另存为时把「编码」选成 `UTF-8`**（默认的 ANSI 会乱码）
2. 然后：

```powershell
Get-Content -Encoding UTF8 article.txt | python scripts\tts.py tts --text - -o out.mp3
```

`--text -` 表示从标准输入读。

如果短文本也乱码，在 PowerShell 里先执行 `chcp 65001` 切到 UTF-8 再跑。

---

## 常用命令速查

Windows 路径用反斜杠，带空格的路径要加引号。

```powershell
# 列音色
python scripts\tts.py voices

# 合成（不指定音色则自动用列表第一个）
python scripts\tts.py tts --text "今天天气不错" -o out.mp3

# 指定音色
python scripts\tts.py tts --text "你好" --voice abc123 -o out.mp3

# 方言
python scripts\tts.py tts --text "巴适得很" --lang sichuan -o out.mp3

# 情绪（只在普通话/英语/日语/西语/阿语下可用）
python scripts\tts.py tts --text "太好啦" --emotion happy=0.8 -o out.mp3

# 音频降噪
python scripts\tts.py denoise --file "C:\audio\noisy.wav" -o clean.wav

# 上传新音色
python scripts\tts.py upload-voice --file sample.wav --name "小王"

# 看全部参数
python scripts\tts.py tts --help
```

---

## 排错

**`python : 无法将"python"项识别为...`**
Python 没装，或者装的时候没勾 `Add python.exe to PATH`。重装一遍，勾上那个选项。

**弹出微软商店**
你敲的是 `python3`。Windows 上用 `python`。

**`错误：未设置环境变量 VOICE_API_KEY`**
`setx` 之后没重开窗口 / 没重启 AutoClaw。见第三步。

**`接口错误：[code=7] sign无效` 或 `sign无效或用户未开通API`**
这不是你这边能修的，是服务端账号状态问题。三种情况：

- key 复制时多了空格或少了字符——重新复制一遍
- 账号的 API 权限没开通（库里 `apiOpen` 不为 2）
- 企业会员已过期

后两种要找平台客服开通，客户端怎么改都没用。
**注意**：同一个 key、同一个请求，报错文案在「sign无效」和「sign无效或用户未开通API」之间反复横跳的话，
说明服务端账号状态本身不稳定，这条信息直接告诉客服，能帮他们定位。

**`[code=1001]`**
单次文本超字数了，默认上限 5000 字符。拆成几段分别合成。

**`暂不支持该语言`**
`--lang` 传的值不在服务端能力表里。去掉 `--lang`，改成 `--style 3`，让模型按文本自己判断。

**中文变成问号或方块**
见上面「中文文本的坑」。

**合成卡住不返回**
脚本最长等 5 分钟。超时会打印 taskId，用 `python scripts\tts.py result <taskId>` 单独查，不要重复提交。

---

## 交给别人时

打包成 zip 发过去，附一句：

> 解压到 `C:\voice-skill`，装 Python 3（勾 Add to PATH），
> PowerShell 跑 `setx VOICE_API_KEY "<key>"` 后重启 AutoClaw，
> 先 `python scripts\tts.py voices` 验证通了再用。

**Key 单独发，别写在文档里、别贴在聊天窗口里。**
