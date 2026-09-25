"""Regenerate the synthetic transcripts in this folder (run by hand, output committed).

Record shapes follow what Claude Code 2.1.281 and codex-cli 0.145.0 write
(observed 2026-09-24); every value is fictional. No secret-shaped token is
written here: tests plant tokens at run time (see tests/test_brain_journal.py).
The NRIC-shaped and Luhn-valid test values below exist to prove redaction.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SID = "11111111-aaaa-4bbb-8ccc-000000000001"
SID2 = "22222222-aaaa-4bbb-8ccc-000000000002"
CWD = "/work/fx"
SCRIPT = ("Decision: let's go with Firebird for the widget ledger. From now on, always answer in bullet points. "
          "No, that's wrong: the client's timezone is SGT, not UTC. If we went with CouchDB instead, would that "
          "be faster? Just thinking out loud. Remind me to send the pricing note to Sam by Friday. "
          "For the form, NRIC S1234567D and test card 4111 1111 1111 1111.")


def base(kind, n, ts, sid=SID, **kw):
    rec = {"type": kind, "uuid": "u-%03d" % n, "parentUuid": "u-%03d" % (n - 1) if n > 1 else None,
           "sessionId": sid, "timestamp": ts, "cwd": CWD, "gitBranch": "main", "version": "2.1.281",
           "entrypoint": "sdk-cli", "isSidechain": False, "userType": "external"}
    rec.update(kw)
    return rec


def channel(user, uid, msg_id, ts, text):
    return ('<channel source="plugin:chat:chat" chat_id="-1" message_id="%s" user="%s" '
            'user_id="%s" ts="%s">%s</channel>' % (msg_id, user, uid, ts, text))


def claude_main():
    t = "2026-09-24T06:05:%02d.000Z"
    return [
        {"type": "queue-operation", "operation": "enqueue", "timestamp": t % 0, "sessionId": SID},
        base("user", 1, t % 1, promptSource="sdk", message={"role": "user", "content": SCRIPT}),
        {"type": "attachment", "attachment": {"type": "hook_success", "hookEvent": "UserPromptSubmit",
                                              "content": "UTC=2026-09-24 06:05:01Z"}, "sessionId": SID},
        base("user", 2, t % 2, isMeta=True, promptSource="system",
             message={"role": "user", "content": "<system-reminder>Project instructions: always dispatch.</system-reminder>"}),
        base("assistant", 3, t % 3, message={"role": "assistant", "content": [{"type": "thinking", "thinking": ""}]}),
        base("assistant", 4, t % 4, message={"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_1", "name": "Write",
             "input": {"file_path": "/work/fx/notes/plan.md", "content": "plan"}}]}),
        base("user", 5, t % 5, message={"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": "File created"}]}),
        base("assistant", 6, t % 6, message={"role": "assistant", "content": [{"type": "text", "text": "OK."}]}),
        base("assistant", 7, t % 7, message={"role": "assistant", "content": [
            {"type": "text", "text": "Noted. We decided to use MongoDB for the ledger."}]}),
        base("user", 8, "2026-09-24T06:10:00.000Z", isMeta=True, promptSource="system", message={
            "role": "user", "content": channel("sam_acme", "4242", "7", "2026-09-24T06:10:00.000Z",
                                               "Decision: we'll use the blue logo for Acme.")}),
        base("user", 9, "2026-09-24T06:11:00.000Z", isMeta=True, promptSource="system", message={
            "role": "user", "content": channel("stranger", "999", "8", "2026-09-24T06:11:00.000Z",
                                               "Decision: let's ship it tonight.")}),
        base("assistant", 10, "2026-09-24T06:11:05.000Z", message={"role": "assistant", "content": [
            {"type": "text", "text": "Noted for Acme."}]}),
        base("user", 11, "2026-09-24T06:12:00.000Z", promptSource="typed", message={"role": "user", "content":
             "<command-name>/wake</command-name>\n<command-message>wake</command-message>\n<command-args></command-args>"}),
        base("user", 12, "2026-09-24T06:12:01.000Z", message={"role": "user", "content": [
            {"type": "text", "text": "[Request interrupted by user]"}]}),
        {"type": "last-prompt", "lastPrompt": "x", "sessionId": SID},
    ]


def claude_external():
    t = "2026-09-24T02:00:%02d.000Z"
    return [
        base("user", 1, t % 1, sid=SID2, promptSource="typed",
             message={"role": "user", "content": "Decision: let's use Stripe for billing on the Acme store."}),
        base("assistant", 2, t % 2, sid=SID2, message={"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_9", "name": "WebSearch", "input": {"query": "stripe fees"}}]}),
        base("user", 3, t % 3, sid=SID2, message={"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_9", "content": "results"}]}),
        base("assistant", 4, t % 4, sid=SID2, message={"role": "assistant", "content": [
            {"type": "text", "text": "Stripe it is."}]}),
    ]


def codex(sid, cwd, user_text, extra_unknown):
    ts = "2026-09-24T07:20:%02d.000Z"
    recs = [
        {"timestamp": ts % 0, "type": "session_meta", "payload": {
            "session_id": sid, "id": sid, "timestamp": ts % 0, "cwd": cwd, "originator": "codex_exec",
            "cli_version": "0.145.0", "source": "exec", "thread_source": "user", "model_provider": "openai",
            "history_mode": "legacy", "git": {}}},
        {"timestamp": ts % 0, "type": "event_msg", "payload": {"type": "task_started", "turn_id": "t1"}},
        {"timestamp": ts % 1, "type": "response_item", "payload": {"type": "message", "role": "developer", "content": [
            {"type": "input_text", "text": "<permissions instructions>sandbox</permissions instructions>"}]}},
        {"timestamp": ts % 1, "type": "response_item", "payload": {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "# AGENTS.md instructions for %s\n\n<INSTRUCTIONS>always dispatch</INSTRUCTIONS>" % cwd},
            {"type": "input_text", "text": "<environment_context>\n  <cwd>%s</cwd>\n</environment_context>" % cwd}]}},
        {"timestamp": ts % 1, "type": "turn_context", "payload": {"turn_id": "t1", "cwd": cwd, "model": "gpt-5.5"}},
        {"timestamp": ts % 2, "type": "response_item", "payload": {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": user_text}]}},
        {"timestamp": ts % 2, "type": "event_msg", "payload": {"type": "user_message", "message": user_text,
                                                               "images": [], "text_elements": []}},
        {"timestamp": ts % 4, "type": "event_msg", "payload": {"type": "agent_message", "message": "OK",
                                                               "phase": "final_answer"}},
        {"timestamp": ts % 4, "type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                                   "content": [{"type": "output_text", "text": "OK"}]}},
    ]
    if extra_unknown:
        recs.append({"timestamp": ts % 5, "type": "future_record_kind", "payload": {"shape": "unknown"}})
    recs.append({"timestamp": ts % 6, "type": "event_msg", "payload": {"type": "task_complete", "turn_id": "t1",
                                                                         "last_agent_message": "OK"}})
    return recs


def gemini(sid):
    """Gemini CLI 0.61.0 chat shape (observed 2026-09-24 in a scratch HOME): header line, a $set with
    the injected <session_context>, then user/gemini records and $set updates."""
    ts = "2026-09-24T09:%02d:00.000Z"
    return [
        {"sessionId": sid, "projectHash": "0" * 64, "startTime": ts % 20, "lastUpdated": ts % 20, "kind": "main"},
        {"$set": {"messages": [{"id": "ctx1", "timestamp": ts % 20, "type": "user",
                                "content": [{"text": "<session_context>\nThis is the Gemini CLI.\n</session_context>"}]}]}},
        {"id": "g-u1", "timestamp": ts % 21, "type": "user",
         "content": [{"text": "Decision: let's go with SQLite for the prototype. From now on, answer tersely."}]},
        {"$set": {"lastUpdated": ts % 21}},
        {"id": "g-a1", "timestamp": ts % 22, "type": "gemini", "content": "OK", "thoughts": [],
         "tokens": {"input": 1, "output": 1}, "model": "gemini-x"},
        {"type": "future_record_kind", "shape": "unknown"},
        {"id": "g-u2", "timestamp": ts % 23, "type": "user", "content": [{"text": "Remind me to back up the prototype."}]},
        {"id": "g-a2", "timestamp": ts % 24, "type": "gemini", "content": "",
         "toolCalls": [{"name": "google_web_search", "args": {"query": "backup"}}]},
        {"id": "g-a3", "timestamp": ts % 25, "type": "gemini", "content": "Noted."},
    ]


def write(path, recs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    write(os.path.join(HERE, "claude", SID + ".jsonl"), claude_main())
    write(os.path.join(HERE, "claude", SID2 + ".jsonl"), claude_external())
    day = os.path.join(HERE, "codexhome", "sessions", "2026", "09", "24")
    write(os.path.join(day, "rollout-2026-09-24T15-20-00-01a0d238-0000-7000-a000-000000000001.jsonl"),
          codex("01a0d238-0000-7000-a000-000000000001", "/tmp/tess-brain-fx",
                "Decision: let's go with Redis for the cache queue. From now on, never use emojis in replies.", True))
    write(os.path.join(day, "rollout-2026-09-24T15-25-00-01a0d238-0000-7000-a000-000000000002.jsonl"),
          codex("01a0d238-0000-7000-a000-000000000002", "/work/other-project",
                "Decision: let's go with Oracle for everything.", False))
    write(os.path.join(HERE, "gemini", "session-2026-09-24T09-20-gem00001.jsonl"),
          gemini("gem00001-aaaa-4bbb-8ccc-000000000001"))
    stdin = os.path.join(HERE, "stdin")
    os.makedirs(stdin, exist_ok=True)
    for name, data in (
        ("session_start.json", {"session_id": SID, "transcript_path": "", "cwd": CWD,
                                "hook_event_name": "SessionStart", "source": "startup"}),
        ("prompt.json", {"session_id": SID, "transcript_path": "", "cwd": CWD, "hook_event_name": "UserPromptSubmit",
                         "prompt": "From now on, always reply in British English."}),
        ("stop.json", {"session_id": SID, "transcript_path": "", "cwd": CWD, "hook_event_name": "Stop",
                       "stop_hook_active": False, "last_assistant_message": "OK."}),
    ):
        with open(os.path.join(stdin, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
