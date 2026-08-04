#!/usr/bin/env python3
"""codex-diff 回归测试：合成 rollout 日志，断言关键行为。

用法: python3 test_codex_diff.py [/path/to/codex-diff]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

TOOL = sys.argv[1] if len(sys.argv) > 1 else "/home/tiger/bin/codex-diff"

FAILS = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   {detail}" if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


def meta(tid, ts, cwd="/tmp/work", parent=None):
    p = {"id": tid, "session_id": tid, "timestamp": ts, "cwd": cwd}
    if parent:
        p["parent_thread_id"] = parent
    return json.dumps({"timestamp": ts, "type": "session_meta", "payload": p}, ensure_ascii=False)


def patch(ts, changes, success=True):
    return json.dumps(
        {"timestamp": ts, "type": "event_msg",
         "payload": {"type": "patch_apply_end", "success": success, "changes": changes}},
        ensure_ascii=False)


def call(ts, name, args):
    return json.dumps(
        {"timestamp": ts, "type": "response_item",
         "payload": {"type": "function_call", "name": name,
                     "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}},
        ensure_ascii=False)


def write_rollout(root, name, lines):
    d = os.path.join(root, "sessions", "2026", "01", "01")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"rollout-{name}.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return p


def run(home, *args):
    env = dict(os.environ, CODEX_HOME=home)
    r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout, r.stderr


def scenario_basic():
    print("\n[1] 补丁类型 / 子线程 / 时序 / 失败标记")
    home = tempfile.mkdtemp()
    P = "019f0000-0000-7000-8000-000000000001"
    C = "019f0000-0000-7000-8000-000000000002"
    write_rollout(home, "p", [
        meta(P, "2026-01-01T00:00:00.000Z"),
        patch("2026-01-01T00:00:10.000Z", {
            "/tmp/work/added.py": {"type": "add", "content": "线一\n线二\n"}}),
        patch("2026-01-01T00:00:30.000Z", {
            "/tmp/work/gone.txt": {"type": "delete", "content": "删掉的内容\n第二行\n"}}),
        patch("2026-01-01T00:00:40.000Z", {
            "/tmp/work/bad.py": {"type": "update", "unified_diff": "@@\n-x\n+y\n"}}, success=False),
        patch("2026-01-01T00:00:50.000Z", {
            "/tmp/work/nocontent.py": {"type": "add"}}),
        patch("2026-01-01T00:01:00.000Z", {
            "/tmp/work/old.py": {"type": "update", "move_path": "/tmp/work/new.py",
                                 "unified_diff": "@@\n-a\n+b\n"}}),
    ])
    write_rollout(home, "c", [
        meta(C, "2026-01-01T00:00:15.000Z", parent=P),
        patch("2026-01-01T00:00:20.000Z", {
            "/tmp/work/child.py": {"type": "update", "unified_diff": "@@\n-1\n+2\n"}}),
    ])
    code, out, err = run(home, P)
    check("add 内容完整输出", "+线一" in out and "+线二" in out)
    check("delete 内容完整输出", "-删掉的内容" in out and "-第二行" in out)
    check("失败补丁被标记", "失败" in out)
    check("改名被标注", "new.py" in out and "改名" in out)
    check("子线程补丁被包含", "child.py" in out)
    check("跨线程按时间排序",
          out.index("added.py") < out.index("child.py") < out.index("gone.txt"),
          "顺序错乱")
    check("add 缺 content 时仍显示文件名", "nocontent.py" in out,
          "只打印了『无 content 记录』，丢失了被新增的文件名")
    check("退出码 0", code == 0, f"code={code} err={err[:200]}")
    shutil.rmtree(home)


def scenario_writes():
    print("\n[2] shell 写盘命令检测（召回 / 误报）")
    home = tempfile.mkdtemp()
    T = "019f0000-0000-7000-8000-00000000000a"
    positives = {
        "重定向": "echo hi > /tmp/x",
        "追加重定向": "echo hi >> /tmp/x",
        "cp": "cp a b",
        "tee": "echo hi | tee /tmp/x",
        "sudo tee -a": "echo hi | sudo tee -a /etc/hosts",
        "wget -O": "wget https://a/b -O /tmp/f",
        "curl -o": "curl -o /tmp/f https://a",
        "curl --output": "curl -sSL https://a --output /tmp/f",
        "git stash": "git stash",
        "sed -i": "sed -i s/a/b/ f.txt",
        "嵌套 bash -c": "bash -c 'echo x > /tmp/y'",
    }
    negatives = {
        "rg 引号内关键词": "rg -n 'rm -rf' file",
        "sed -n 读取": "sed -n 1,5p codex-diff",
        "重定向到 /dev/null": "ls foo > /dev/null",
        "纯读取": "cat /etc/hosts",
        "bash -lc 包装纯读取": "bash -lc 'ls -la'",
    }
    lines = [meta(T, "2026-01-01T00:00:00.000Z")]
    for i, c in enumerate(list(positives.values()) + list(negatives.values())):
        lines.append(call(f"2026-01-01T00:0{i//10}:{i%10:02d}.000Z", "exec_command",
                          {"cmd": c, "workdir": "/tmp/work"}))
    write_rollout(home, "w", lines)
    code, out, err = run(home, T)

    # 当前设计：所有 shell 调用都列出，靠标签区分「疑似写入」/「保守列出」。
    def label_of(cmd):
        blocks = out.split("--- shell ")
        for b in blocks[1:]:
            if f"$ {cmd}" in b:
                return b.split("]")[0].lstrip("[")
        return None

    for name, c in positives.items():
        check(f"标为疑似写入: {name}", label_of(c) == "疑似写入",
              f"`{c}` 的标签是 {label_of(c)!r}")
    for name, c in negatives.items():
        check(f"标为保守列出: {name}", label_of(c) == "保守列出",
              f"`{c}` 的标签是 {label_of(c)!r}")
    shutil.rmtree(home)


def scenario_cmd_shapes():
    print("\n[3] 命令参数的各种形态")
    home = tempfile.mkdtemp()
    T = "019f0000-0000-7000-8000-00000000000b"
    write_rollout(home, "s", [
        meta(T, "2026-01-01T00:00:00.000Z"),
        call("2026-01-01T00:00:01.000Z", "exec_command", {"cmd": "echo A > /tmp/a"}),
        call("2026-01-01T00:00:02.000Z", "shell", {"command": ["bash", "-lc", "echo B > /tmp/b"]}),
        call("2026-01-01T00:00:03.000Z", "write_stdin", {"chars": "echo C > /tmp/c\n"}),
        call("2026-01-01T00:00:04.000Z", "exec",
             'await tools.exec_command({cmd: "echo D > /tmp/d", workdir: "/tmp"})'),
        call("2026-01-01T00:00:05.000Z", "exec_command", {"cmd": "echo E > /tmp/e"}),
        call("2026-01-01T00:00:06.000Z", "exec_command", {"cmd": "echo E > /tmp/e"}),
    ])
    code, out, err = run(home, T)
    for label, needle in [("cmd 字段", "/tmp/a"), ("command 列表", "/tmp/b"),
                          ("write_stdin", "/tmp/c"), ("JS exec 包装", "/tmp/d")]:
        check(f"识别 {label}", needle in out, f"未检出 {needle}")
    check("重复命令不去重", out.count("echo E > /tmp/e") == 2,
          f"出现 {out.count('echo E > /tmp/e')} 次，应为 2")
    shutil.rmtree(home)


def scenario_cli():
    print("\n[4] CLI 行为")
    home = tempfile.mkdtemp()
    A = "019f0000-0000-7000-8000-0000000000c1"
    B = "019f0000-0000-7000-8000-0000000000c2"
    write_rollout(home, "a", [meta(A, "2026-01-01T00:00:00.000Z")])
    write_rollout(home, "b", [meta(B, "2026-01-02T00:00:00.000Z")])
    code, out, _ = run(home, "-n")
    check("-n 列出两个会话", A in out and B in out)
    check("-n 最新在前", out.index(B) < out.index(A))
    code, out, _ = run(home)          # 默认取最新
    check("默认选最新会话", B in out.splitlines()[0])
    code, out, _ = run(home, "0000000000c1")
    check("唯一后缀不算前缀匹配", code != 0 or A in out)
    code, out, err = run(home, "019f0000-0000-7000-8000-0000000000")
    check("前缀不唯一时报错", code != 0 and ("不唯一" in err + out), f"code={code}")
    # 损坏日志 -> 非零退出
    d = os.path.join(home, "sessions", "2026", "01", "01")
    with open(os.path.join(d, "rollout-broken.jsonl"), "w") as f:
        f.write(meta("019f0000-0000-7000-8000-0000000000c3", "2026-01-03T00:00:00.000Z") + "\n")
        f.write("{ this is not json\n")
    code, out, err = run(home, "019f0000-0000-7000-8000-0000000000c3")
    check("损坏记录 -> 非零退出", code != 0, f"code={code}")
    check("损坏记录 -> stderr 有警告", "警告" in err or "warn" in err.lower())
    shutil.rmtree(home)


def scenario_summary_and_exit():
    print("\n[5] 文件级摘要 / 归档目录 / 退出码分级")
    home = tempfile.mkdtemp()
    T = "019f0000-0000-7000-8000-0000000000d1"
    write_rollout(home, "s", [
        meta(T, "2026-01-01T00:00:00.000Z"),
        patch("2026-01-01T00:00:10.000Z", {
            "/tmp/work/a.py": {"type": "add", "content": "x\ny\nz\n"}}),
        patch("2026-01-01T00:00:20.000Z", {
            "/tmp/work/b.py": {"type": "update", "unified_diff": "--- a\n+++ b\n@@\n-1\n+2\n+3\n"}}),
        patch("2026-01-01T00:00:30.000Z", {
            "/tmp/work/c.py": {"type": "delete", "content": "p\nq\n"}}),
        patch("2026-01-01T00:00:40.000Z", {
            "/tmp/work/d.py": {"type": "update", "unified_diff": "@@\n-1\n+2\n"}}, success=False),
    ])
    code, out, _ = run(home, T)
    check("有摘要段", "=== apply_patch 摘要:" in out)
    check("摘要计入 3 个文件", "3 个文件落盘" in out)
    check("摘要单列失败补丁", "1 个补丁应用失败" in out)
    check("摘要标 A/+行数", "A /tmp/work/a.py" in out and "+3" in out)
    check("摘要标 M/加减行", "M /tmp/work/b.py" in out and "+2 -1" in out)
    check("摘要标 D", "D /tmp/work/c.py" in out)
    check("干净会话退出 0", code == 0, f"code={code}")

    # 软问题（启发式不确定）-> 1
    T2 = "019f0000-0000-7000-8000-0000000000d2"
    write_rollout(home, "soft", [
        meta(T2, "2026-01-02T00:00:00.000Z"),
        json.dumps({"timestamp": "2026-01-02T00:00:01.000Z", "type": "response_item",
                    "payload": {"type": "custom_tool_call", "name": "exec",
                                "arguments": "const files=[1,2].map(i=>`f${i}`);"
                                             "await tools.exec_command({cmd: files[0]})"}},
                   ensure_ascii=False),
    ])
    code, out, err = run(home, T2)
    check("仅启发式不确定 -> 退出 1", code == 1, f"code={code} err={err[:160]}")

    # 硬问题（日志损坏）-> 2
    T3 = "019f0000-0000-7000-8000-0000000000d3"
    d = os.path.join(home, "sessions", "2026", "01", "01")
    with open(os.path.join(d, "rollout-hard.jsonl"), "w", encoding="utf-8") as f:
        f.write(meta(T3, "2026-01-03T00:00:00.000Z") + "\n{ broken json\n")
    code, out, err = run(home, T3)
    check("日志损坏 -> 退出 2", code == 2, f"code={code}")

    # archived_sessions 也要能查到
    T4 = "019f0000-0000-7000-8000-0000000000d4"
    ad = os.path.join(home, "archived_sessions", "2026", "01", "01")
    os.makedirs(ad, exist_ok=True)
    with open(os.path.join(ad, "rollout-arch.jsonl"), "w", encoding="utf-8") as f:
        f.write(meta(T4, "2026-01-04T00:00:00.000Z") + "\n")
        f.write(patch("2026-01-04T00:00:01.000Z",
                      {"/tmp/work/arch.py": {"type": "add", "content": "归档\n"}}) + "\n")
    code, out, _ = run(home, T4)
    check("归档会话可查到", "arch.py" in out and "+归档" in out)
    shutil.rmtree(home)


for fn in (scenario_basic, scenario_writes, scenario_cmd_shapes, scenario_cli,
           scenario_summary_and_exit):
    fn()

print("\n" + "=" * 60)
if FAILS:
    print(f"失败 {len(FAILS)} 项:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("全部通过")
