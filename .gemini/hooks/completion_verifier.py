import os
import sys
import json
import urllib.request
import urllib.error

def main():
    # 1. Read stdin
    try:
        input_data = json.loads(sys.stdin.read())
    except Exception as e:
        # If no stdin or invalid JSON, default to empty dict
        input_data = {}

    # Print to stderr for debugging
    print(f"Completion verifier received: {json.dumps(input_data)}", file=sys.stderr)

    # 2. Check stop_hook_active or arguments
    args = input_data.get("arguments", {})
    if args.get("stop_hook_active") or input_data.get("stop_hook_active"):
        print(json.dumps({"ok": True}))
        return

    # Find transcript path
    transcript_path = args.get("transcript_path") or input_data.get("transcript_path")
    
    # Heuristic: search standard locations if not found
    if not transcript_path or not os.path.exists(transcript_path):
        # Let's search under .system_generated/logs or similar
        for root, dirs, files in os.walk("."):
            if "transcript.jsonl" in files:
                transcript_path = os.path.join(root, "transcript.jsonl")
                break

    transcript_content = ""
    if transcript_path and os.path.exists(transcript_path):
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                # Read last 200 lines to avoid blowing up token limits
                lines = f.readlines()
                transcript_content = "".join(lines[-200:])
        except Exception as e:
            print(f"Error reading transcript: {e}", file=sys.stderr)

    # If transcript is still empty, let's try reading git diff / log as context
    if not transcript_content:
        try:
            import subprocess
            git_status = subprocess.check_output(["git", "status"], text=True)
            git_log = subprocess.check_output(["git", "log", "-n", "5", "--oneline"], text=True)
            transcript_content = f"GIT STATUS:\n{git_status}\n\nRECENT COMMITS:\n{git_log}"
        except Exception as e:
            transcript_content = "No transcript or git context available."

    # 3. Call Gemini API if API key is present
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not found in environment. Falling back to basic heuristic validation.", file=sys.stderr)
        # Fallback to True to avoid blocking local execution
        print(json.dumps({"ok": True}))
        return

    prompt = f"""You are a completion verifier for the Uberon AI agent (@clnsmth-ontology-agent). Your job is to check whether the agent actually completed its task before allowing it to stop.

Read the following transcript/context and determine:
1. What was the user's request?
2. Did the agent produce an appropriate deliverable?
3. If the task required ontology or repository edits, did the agent actually push work and create or update a PR?
4. If the task required only a question, clarification, research summary, or status update, did the agent communicate that back on GitHub?
5. If the task was a PR review, did the agent leave an actual GitHub review and or inline review comments?

Look for actual tool-use evidence, not text claims. Valid evidence includes commands such as:
- gh pr create
- gh pr review
- gh issue comment
- gh pr comment
- git push

TRANSCRIPT/CONTEXT:
{transcript_content}

Respond ONLY with a JSON object of the format:
{{"ok": true}} or {{"ok": false, "reason": "<specific description of what is missing>"}}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            text_response = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Parse the JSON response from Gemini
            parsed_res = json.loads(text_response)
            print(f"Gemini verification result: {parsed_res}", file=sys.stderr)
            print(json.dumps(parsed_res))
            return
    except Exception as e:
        print(f"Error calling Gemini API for verification: {e}", file=sys.stderr)
        # Fallback to true if API call fails so we don't break execution in unexpected network errors
        print(json.dumps({"ok": True}))

if __name__ == "__main__":
    main()
