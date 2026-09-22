#!/usr/bin/env python3
"""语音开放接口命令行封装。

只依赖 Python 3 标准库，无需 pip install。

  export VOICE_API_KEY=<你的sign>
  python3 tts.py voices
  python3 tts.py tts --text "今天天气不错" -o out.mp3
  python3 tts.py tts --text "巴适得很" --lang sichuan -o out.mp3
  python3 tts.py tts --text "太好啦" --emotion happy=0.8 -o out.mp3
  python3 tts.py design --text "欢迎光临" --describe "沉稳低沉的男声" -o out.mp3
  python3 tts.py denoise --file noisy.wav -o clean.wav

设计原则：调用方只管"说什么、用谁的声音、什么语言、什么情绪"，
style / genre / 建任务+轮询这些接口细节由本脚本处理，避免踩参数坑。
"""

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

DEFAULT_BASE = "https://openapi.anyvoice.cn"

# 支持情绪控制的语言（走 style=2 / V2.5）。其余语言一律 style=3（方言/多语言模型）。
EMOTION_LANGS = {"mandarin", "english", "ja", "es", "ar"}

EMOTION_DIMENSIONS = (
    "happy", "angry", "sad", "afraid",
    "disgusted", "melancholic", "surprised", "calm",
)

POLL_INTERVAL = 2
POLL_TIMEOUT = 300


class ApiError(Exception):
    """业务码非 0，msg 是服务端返回的中文原因。"""


def base_url():
    return os.environ.get("VOICE_API_BASE", DEFAULT_BASE).rstrip("/")


def api_key():
    key = os.environ.get("VOICE_API_KEY", "").strip()
    if not key:
        sys.exit("错误：未设置环境变量 VOICE_API_KEY（企业 API Key / sign）")
    return key


def request(method, path, query=None, body=None, files=None, raw=False):
    """发一个请求并拆掉 {code,msg,data} 信封，返回 data。

    raw=True 时直接返回响应字节（用于文件下载）。
    """
    url = base_url() + path
    if query:
        pairs = [(k, str(v)) for k, v in query.items() if v is not None]
        url += "?" + urllib.parse.urlencode(pairs)

    headers = {"sign": api_key()}
    data = None
    if files is not None:
        data, content_type = encode_multipart(files, body or {})
        headers["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        raise ApiError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}")
    except urllib.error.URLError as exc:
        raise ApiError(f"网络错误: {exc.reason}")

    if raw:
        return payload

    try:
        envelope = json.loads(payload)
    except json.JSONDecodeError:
        raise ApiError(f"响应不是 JSON: {payload[:200]!r}")

    # 接口用 code 表达成败，HTTP 状态码一直是 200，必须判 code
    if envelope.get("code") != 0:
        raise ApiError(f"[code={envelope.get('code')}] {envelope.get('msg', '未知错误')}")
    return envelope.get("data")


def encode_multipart(files, fields):
    boundary = uuid.uuid4().hex
    buf = bytearray()
    for name, value in fields.items():
        buf += f"--{boundary}\r\n".encode()
        buf += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        buf += f"{value}\r\n".encode()
    for name, path in files.items():
        filename = os.path.basename(path)
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            content = fh.read()
        buf += f"--{boundary}\r\n".encode()
        buf += (
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        ).encode()
        buf += f"Content-Type: {ctype}\r\n\r\n".encode()
        buf += content + b"\r\n"
    buf += f"--{boundary}--\r\n".encode()
    return bytes(buf), f"multipart/form-data; boundary={boundary}"


def parse_emotion(pairs):
    """--emotion happy=0.8 --emotion calm=0.2  ->  {"happy":0.8,"calm":0.2}"""
    ext = {}
    for item in pairs or []:
        if "=" not in item:
            sys.exit(f"错误：--emotion 格式应为 维度=强度，收到 {item!r}")
        name, _, value = item.partition("=")
        name = name.strip()
        if name not in EMOTION_DIMENSIONS:
            sys.exit(f"错误：未知情绪维度 {name!r}，可选：{', '.join(EMOTION_DIMENSIONS)}")
        try:
            strength = float(value)
        except ValueError:
            sys.exit(f"错误：情绪强度必须是数字，收到 {value!r}")
        if not 0 <= strength <= 1:
            sys.exit(f"错误：情绪强度需在 0~1 之间，收到 {strength}")
        ext[name] = strength
    return ext


def pick_style(lang):
    """由语言推导 style，调用方不必理解 1/2/3。"""
    if lang and lang not in EMOTION_LANGS:
        return "3"
    return "2"


def first_voice():
    data = request("GET", "/api/third/reference/list", query={"page": 1, "pageSize": 1})
    items = (data or {}).get("list") or []
    if not items:
        sys.exit("错误：账号下没有任何音色，请先用 upload-voice 上传参考音频")
    # 接口返回字段是 audioId（不是 roleId）；兼容老响应保留 roleId 回退
    return items[0].get("audioId") or items[0]["roleId"]


def download(url, out_path):
    req = urllib.request.Request(url, headers={"sign": api_key()})
    with urllib.request.urlopen(req, timeout=120) as resp:
        content = resp.read()
    with open(out_path, "wb") as fh:
        fh.write(content)
    return out_path


# ---------------------------------------------------------------- 子命令

def cmd_voices(args):
    data = request(
        "GET", "/api/third/reference/list",
        query={"page": args.page, "pageSize": args.page_size},
    )
    items = (data or {}).get("list") or []
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return
    if not items:
        print("（账号下暂无音色）")
        return
    print(f"共 {data.get('total', len(items))} 个音色：")
    for item in items:
        print(f"  {item.get('audioId') or item.get('roleId')}\t{item.get('name', '')}")


def cmd_upload_voice(args):
    data = request(
        "POST", "/api/third/reference/upload",
        files={"file": args.file},
        body={"name": args.name, "describe": args.describe or ""},
    )
    print(f"音色已创建：{data.get('audioId')}  {data.get('name', '')}")


def cmd_tts(args):
    text = args.text
    if text == "-":
        text = sys.stdin.read()
    text = text.strip()
    if not text:
        sys.exit("错误：--text 为空")

    ext = parse_emotion(args.emotion)
    voice = args.voice or first_voice()
    style = args.style or pick_style(args.lang)

    if ext and style != "2":
        sys.exit(
            f"错误：情绪控制只在 style=2 生效，而语言 {args.lang!r} 会走 style=3。\n"
            f"      请改用支持情绪的语言（{', '.join(sorted(EMOTION_LANGS))}），或去掉 --emotion。"
        )

    payload = {"content": text, "audioId": voice, "style": style, "speed": args.speed}
    if args.lang:
        payload["targetSpeech"] = args.lang
    if ext:
        payload["genre"] = 1
        payload["ext"] = ext

    try:
        result = request("POST", "/api/third/tts/create", body=payload)
    except ApiError as exc:
        if "暂不支持该语言" in str(exc):
            sys.exit(
                f"{exc}\n提示：该语言不在服务端能力表内。改为不传 --lang 并加 --style 3 重试，"
                "方言/多语言模型会按文本自行判断。"
            )
        raise

    task_id = result.get("taskId")
    status = result.get("status")

    # create 立刻返回 taskId（status=1），结果靠轮询 /tts/result 拿
    deadline = time.time() + POLL_TIMEOUT
    while status not in (2, 3) and time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        result = request("GET", "/api/third/tts/result", query={"taskId": task_id})
        status = result.get("status")

    if status == 3:
        sys.exit(f"合成失败（taskId={task_id}）")
    if status != 2:
        sys.exit(f"合成超时，任务仍在处理。稍后用 result 子命令查询：taskId={task_id}")

    url = result.get("voiceUrl")
    if args.output:
        print(download(url, args.output))
    else:
        print(url)


def cmd_design(args):
    """声音设计：不用参考音频，直接描述或选方言参数生成音色并合成。"""
    text = args.text
    if text == "-":
        text = sys.stdin.read()
    text = text.strip()
    if not text:
        sys.exit("错误：--text 为空")

    dialect_opts = {
        "language": args.lang, "gender": args.gender, "age": args.age,
        "pitch": args.pitch, "voiceStyle": args.voice_style, "accent": args.accent,
    }
    given = {k: v for k, v in dialect_opts.items() if v}

    if args.describe:
        # 描述设计：engine=1，其余参数无意义
        if given:
            sys.exit(
                f"错误：--describe 走描述设计（engine=1），"
                f"{'/'.join(sorted(given))} 不会生效。二选一。"
            )
        payload = {"content": text, "engine": 1, "description": args.describe}
    else:
        if not given:
            sys.exit("错误：请用 --describe 描述音色，或至少给一个方言设计参数（--lang/--gender/...）")
        if args.accent and args.lang != "english":
            sys.exit("错误：--accent 只在 --lang english 时可用")
        payload = {"content": text, "engine": 2, **given}

    data = request("POST", "/api/third/dubbing/create", body=payload)
    dubb_id = data.get("dubbId")

    deadline = time.time() + POLL_TIMEOUT
    status = 1
    while status not in (2, 3) and time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        result = request("GET", "/api/third/dubbing/result", query={"dubbId": dubb_id})
        status = result.get("status")

    if status == 3:
        sys.exit(f"声音设计失败（dubbId={dubb_id}）")
    if status != 2:
        sys.exit(f"声音设计超时，任务仍在处理：dubbId={dubb_id}")

    url = result.get("voiceUrl")
    # 设计结果只保留 1 天，且不会变成可复用音色，想留住就得下载
    print(download(url, args.output) if args.output else url)


def cmd_result(args):
    result = request("GET", "/api/third/tts/result", query={"taskId": args.task_id})
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_denoise(args):
    data = request("POST", "/api/third/denoise/upload", files={"file": args.file})
    task_id = data.get("taskId")

    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        result = request("GET", "/api/third/denoise/poll", query={"taskId": task_id})
        status = result.get("status")
        if status == "completed":
            url = result.get("filePath")
            print(download(url, args.output) if args.output else url)
            return
        if status == "failed":
            sys.exit(f"降噪失败：{result.get('message', '未知原因')}")
    sys.exit(f"降噪超时，taskId={task_id}")


def main():
    parser = argparse.ArgumentParser(
        description="语音开放接口命令行封装（TTS / 音色 / 降噪）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("voices", help="列出账号下的音色")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=30, help="最大 30")
    p.add_argument("--json", action="store_true", help="输出原始 JSON")
    p.set_defaults(func=cmd_voices)

    p = sub.add_parser("upload-voice", help="上传参考音频，创建新音色")
    p.add_argument("--file", required=True, help="音频文件路径")
    p.add_argument("--name", required=True, help="音色名称")
    p.add_argument("--describe", help="音色描述")
    p.set_defaults(func=cmd_upload_voice)

    p = sub.add_parser("tts", help="文本转语音（异步创建任务并自动轮询到出结果）")
    p.add_argument("--text", required=True, help="要合成的文本，传 - 表示从 stdin 读")
    p.add_argument("--voice", help="音色 ID，不传则自动用列表里第一个")
    p.add_argument("--lang", help="目标语言/方言，如 mandarin/english/sichuan/yue/ja；不传则服务端按文本自动判定")
    p.add_argument("--speed", type=float, default=1.0, help="语速 0.5~2.0，默认 1.0")
    p.add_argument("--emotion", action="append", metavar="维度=强度",
                   help=f"情绪向量，可重复。维度：{', '.join(EMOTION_DIMENSIONS)}")
    p.add_argument("--style", choices=["1", "2", "3"], help="手动指定模型版本，一般不需要")
    p.add_argument("-o", "--output", help="保存到本地文件；不传则只打印 URL")
    p.set_defaults(func=cmd_tts)

    p = sub.add_parser("design", help="声音设计：无需参考音频，描述或选方言参数直接生成音频")
    p.add_argument("--text", required=True, help="要合成的文本，最长 1000 字节；传 - 表示从 stdin 读")
    p.add_argument("--describe", help="音色描述，如「沉稳低沉的男声，语速偏慢」。与下面的方言参数二选一")
    p.add_argument("--lang", help="语言/方言：sichuan/northeast/henan/... 或 chinese/cantonese/minnan/uyghur/english")
    p.add_argument("--gender", choices=["male", "female"])
    p.add_argument("--age", choices=["child", "teen", "youth", "middle_aged", "elderly"])
    p.add_argument("--pitch", choices=["very_low", "low", "medium", "high", "very_high"])
    p.add_argument("--voice-style", choices=["whisper"], help="留空=自然")
    p.add_argument("--accent", choices=["american", "british", "australian", "canadian", "indian",
                                        "chinese", "korean", "japanese", "portuguese", "russian"],
                   help="英文口音，仅 --lang english 可用")
    p.add_argument("-o", "--output", help="保存到本地文件；不传则只打印 URL（结果仅保留 1 天）")
    p.set_defaults(func=cmd_design)

    p = sub.add_parser("result", help="按 taskId 查询合成结果")
    p.add_argument("task_id")
    p.set_defaults(func=cmd_result)

    p = sub.add_parser("denoise", help="音频降噪（3~60 秒）")
    p.add_argument("--file", required=True, help="待降噪音频路径")
    p.add_argument("-o", "--output", help="保存到本地文件；不传则只打印 URL")
    p.set_defaults(func=cmd_denoise)

    args = parser.parse_args()
    try:
        args.func(args)
    except ApiError as exc:
        sys.exit(f"接口错误：{exc}")
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
