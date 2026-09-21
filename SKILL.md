---
name: openapi
description: Use when the task needs text-to-speech / voice cloning / audio denoise via this voice open API — synthesizing speech from text, listing or uploading voice clone models (音色/参考音频), emotion-controlled TTS, dialect & multilingual TTS, or denoising an audio file. Covers auth (sign header), all /api/third/* endpoints, parameter rules, the polling workflow, and how to troubleshoot poor synthesis results (mispronunciation, odd pauses, voice not matching, flat emotion) instead of blindly retrying.
---

# OpenAPI (语音开放接口)

TTS / 声音克隆 / 音频降噪 的 HTTP 接口。文本进，音频 URL 出。

- **Base URL**: `https://openapi.anyvoice.cn`
- **鉴权**: 每个请求带 header `sign: <API_KEY>`（也可用 query `?sign=`，但优先用 header）。API Key 是旗舰会员的密钥，向平台申请；过期或未开通 API 会返回「sign无效」/「旗舰会员已过期」。
- **机读 spec**: `GET /api/third/openapi.json`（无需鉴权，OpenAPI 3.0，可直接导入 Coze / Dify / 飞书等平台）。

## 通用响应格式

所有 JSON 接口统一返回：

```json
{ "code": 0, "msg": "操作成功", "data": { } }
```

- `code`: `0`=成功，`7`=通用失败，`1001`=字数超限。**永远先判 `code`，不要只看 HTTP 状态码**（失败时 HTTP 仍可能是 200）。
- 失败时 `msg` 是中文原因，直接透传给用户即可。

## 优先用封装脚本

`scripts/tts.py` 已把鉴权、参数推导、轮询、下载全部封装好，**只依赖 Python 3 标准库**。
能执行命令时一律走脚本，不要自己手拼 curl —— 下面「参数规则」里那些坑脚本都处理了。

```bash
export VOICE_API_KEY=<你的sign>          # 必需
export VOICE_API_BASE=https://...        # 可选，默认 https://openapi.anyvoice.cn

python3 scripts/tts.py voices                                   # 列出可用音色
python3 scripts/tts.py tts --text "今天天气不错" -o out.mp3       # 合成（不传 --voice 自动用第一个音色）
python3 scripts/tts.py tts --text "巴适得很" --lang sichuan -o out.mp3
python3 scripts/tts.py tts --text "太好啦" --emotion happy=0.8 -o out.mp3
python3 scripts/tts.py tts --text - -o out.mp3 < article.txt     # 长文本从 stdin
python3 scripts/tts.py denoise --file noisy.wav -o clean.wav
python3 scripts/tts.py upload-voice --file sample.wav --name "小王"
```

脚本会自动：按 `--lang` 推导 `style`、把 `--emotion` 转成 `genre=1`+`ext`、
`sync` 超时后继续轮询 `result`、`-o` 时下载音频到本地并打印路径。
不传 `-o` 只打印 URL，方便管道接后续处理。

## 直接调 HTTP（没有脚本执行能力时）

合成一段语音的最短路径：

1. `GET /api/third/reference/list` 拿到 `audioId`（声音模型 ID）
2. `POST /api/third/tts/sync`，body 里 `audioId` = 上一步的 `audioId`
3. 返回 `status=2` 时取 `voiceUrl` 即为音频地址

若 `sync` 返回 `status=1`（超过 90 秒仍在处理），拿 `taskId` 去轮询 `GET /api/third/tts/result`。

```bash
curl -X POST https://openapi.anyvoice.cn/api/third/tts/sync \
  -H "sign: $VOICE_API_KEY" -H "Content-Type: application/json" \
  -d '{"content":"今天天气不错","audioId":"<audioId>","style":"2","speed":1.0,"targetSpeech":"mandarin"}'
```

## 接口清单

所有路径前缀 `/api/third`，均需 `sign` 头（`openapi.json` 除外）。

### 语音合成

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/tts/sync` | **首选**。同步合成，服务端内部最多轮询 90s，一次调用拿结果 |
| POST | `/tts/create` | 异步创建任务，立刻返回 `taskId` |
| GET | `/tts/result?taskId=` | 查询任务结果 |
| GET | `/tts/list?page=1&pageSize=10` | 合成历史列表，`pageSize` 最大 30 |

`/tts/sync` 和 `/tts/create` 的请求体相同：

```jsonc
{
  "content": "要合成的文本",   // 必填。长度有上限（按 UTF-8 字节计），超出 code=1001
  "audioId": "声音模型ID",    // 必填，来自 /reference/list 或 /reference/upload 返回的 audioId
  "style":   "2",             // 必填，字符串！"1"=V2.0  "2"=V2.5(支持情绪)  "3"=方言/多语言
  "speed":   1.0,             // 选填，0.5~2.0，一位小数，默认 1.0
  "targetSpeech": "mandarin", // 选填但强烈建议传，见下方语言表
  "genre":   0,               // 选填，情绪控制方式，仅 style="2" 生效
  "ext":     { "happy": 0.8 },// genre=1 时使用的情绪向量
  "emotionPath": "xxx.mp3"    // genre=2 时必填，来自 /file/uploadCustom
}
```

响应 `data`：

```json
{ "taskId": "...", "status": 2, "voiceUrl": "https://..." }
```

`status`: `1`=处理中，`2`=已完成（此时才有 `voiceUrl`），`3`=失败。

### 音色 / 参考音频（克隆模型）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/reference/list?page=1&pageSize=10` | 声音模型列表（含接口上传的与网页端创建的），返回 `list[].audioId / name / describe`，`pageSize` 最大 30 |
| POST | `/reference/upload` | multipart：`file`(音频) + `name`(必填) + `describe`(选填)，返回 `audioId` |
| DELETE | `/reference/delete?audioId=` | 删除音色 |

### 情绪参考音频（临时文件）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/file/uploadCustom` | multipart `file`，mp3/wav/m4a，2–60 秒，≤50MB。返回 `{"emotionPath":"文件名"}`，填回 TTS 的 `emotionPath` |

临时文件会被定时清理，过期需重新上传。

### 降噪

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/denoise/upload` | multipart `file`，时长 3–60 秒。返回 `{"taskId":"..."}` |
| GET | `/denoise/poll?taskId=` | 返回 `{"status":"processing\|completed\|failed","filePath":"...","message":"..."}` |

单用户进行中的降噪任务上限 5 个。

### 文件下载

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/file/download/{filename}` | 下载属于自己的文件；文件名不得含 `/`、`\`、`..` |

## 参数规则（容易踩的坑）

**style 是字符串**，不是数字：`"style": "2"` ✅，`"style": 2` ❌（会返回类型错误）。

**style 与能力的对应**：

- `"1"` V2.0：基础合成，`genre` 只能传 0。
- `"2"` V2.5：**唯一支持情绪控制**的版本。
- `"3"` 方言/多语言：**不支持情绪控制**。接口会放行 `genre`/`ext`/`emotionPath`，但不生效 —— 传了也不报错，别以为生效了。

**style 会被服务端改写**：传了 `targetSpeech` 而该语言不支持所选 style 时，服务端强制改成 `"3"`，响应里返回的是改写后的值。

**speed**：入参校验上限 2.0；方言/多语言链路模型上限只有 1.5，服务端下发前自动压缩，不影响入参。

**情绪控制三选一（仅 style="2"）**：

- `genre: 0` — 跟随参考音频情绪（默认，无需额外参数）
- `genre: 1` — 情绪向量，用 `ext` 指定，8 个维度：`happy / angry / sad / afraid / disgusted / melancholic / surprised / calm`，各取值 `[0,1]`，可同时给多个。**传未知字段会直接报错**。
- `genre: 2` — 情绪参考音频，先 `/file/uploadCustom` 拿文件名，填 `emotionPath`

Web 端情绪控制属专业会员能力；用旗舰会员 API Key 调本接口默认可用，无需额外开通。

**targetSpeech（目标语言/方言）**：非必填但**推荐显式提交**。不传时服务端按文本自动判定，短文本或中英混排容易判错。

- `mandarin` / `english`：style 1/2/3 都支持，可用情绪控制
- `ja` / `es` / `ar`：style="2" 可用情绪控制；style="1" 会被升为 "3"
- 其余（14 种中文方言 + 7 种民族语言 + 40 种独立语言）：**style 传 "3"**，不支持情绪控制
- **枚举外的语言**：传枚举外的值会直接报错「暂不支持该语言」且任务不会创建。这种情况改为 `style="3"` 且 **完全不传 `targetSpeech`**，由方言/多语言模型按文本自行处理，常见语种都能正常合成。

取值清单见同目录 `target-speech-enum.csv`（值 / 名称 / 说明三列）。注意该 csv 与
`/api/third/openapi.json` 里的枚举都只收录了 57 个，而服务端能力表实际已支持 100+ 个语种，
**csv 里没有不代表不支持**，可直接试传；被拒时才按上面的办法回退。常用：`mandarin english yue nan sichuan northeast henan shaanxi ja ko es fr de ru pt it th vi id ms ar hi tr`。

## 配额

- 单次请求文本长度：有上限，按 **UTF-8 字节**计（一个汉字 3 字节），额度随账号而定，超出返回 `code=1001` —— 超了就拆分分段合成
- 并发/在途任务数：默认 **30**（账号可加量）
- 列表类接口 `pageSize` 上限 30

## 轮询建议

用 `/tts/create` 时，建议 2 秒一次轮询 `/tts/result`，直到 `status` 变为 2 或 3。`/tts/sync` 内部就是这个逻辑（2s 间隔、90s 上限），超时会带着 `taskId` 返回 `status=1`，此时继续用 `/tts/result` 兜底，不要重复创建任务。


## 合成效果排查（结果不理想时必读）

用户说「念错了 / 不像 / 太平淡 / 停顿奇怪」时，**不要用同一组参数反复重试**。
先按下表定位原因，把对应建议**主动讲给用户**，等用户改完文本或重新给参考音频，再调一次接口。

| 现象 | 告诉用户怎么改 | 接口侧怎么配合 |
|---|---|---|
| 某个字念错、多音字读错 | 把生僻字/多音字换成**同音字**；数字、单位、英文缩写改成汉字写法（「2026 年」→「二零二六年」，「3kg」→「三公斤」） | 只改 `content`，其余参数不动，重调 `/tts/sync` |
| 停顿生硬、断句奇怪 | 在异常停顿处**增删标点**（逗号短停、句号长停），长句拆成短句 | 只改 `content`；长文按 150–250 字分段顺序合成 |
| 念出了奇怪的符号 | 删掉表情符号、Markdown 标记、括号注释、连续空行等**不该念出来的字符** | 提交前先清洗 `content` |
| 音色不像本人 | 换一段**底噪更小、空白更少**的参考音频，3–10 秒清晰干声最佳 | 先 `/denoise/upload` 降噪，再 `/reference/upload` 重建音色 |
| 语气太平、没有情绪 | 告诉用户可以直接指定情绪，不必在参考音频里演 | `style="2"` + `genre=1` 传 `ext` 情绪向量，或 `genre=2` 传 `emotionPath` |
| 语速不合适 | 问清想要的快慢再整体调整 | `speed` 0.5–2.0（方言/多语言链路实际上限 1.5） |
| 方言/外语读成了普通话 | 确认目标语种，提醒一段文本只写一种语言 | 显式传 `targetSpeech`，方言与小语种配 `style="3"` |

**参考音频怎么录才像**：3–60 秒、推荐 3–10 秒；单人、清晰、无背景音乐与混响；底噪越小、空白越少越像；
嘈杂录音先走 `/denoise/upload` 降噪再克隆；用平时说话的状态录，不要刻意表演——情绪交给 `style="2"` 的参数控制。

**文本怎么写才自然**：一段只写一种语言；长文按自然段切 150–250 字，用同一个 `audioId` 顺序合成再拼接，
音色和语气才连贯；中英混排时务必显式传 `targetSpeech`。

更细的说明见所接入平台的开发者文档「配音技巧 / 效果调优」一节。
