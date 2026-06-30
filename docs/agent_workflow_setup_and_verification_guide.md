# Setup and Verification Guide for `@clnsmth-ai-agent`

This guide outlines the manual configuration steps and tests required to transition the Uberon fork's agentic workflows to Google Gemini and run under the `@clnsmth-ai-agent` GitHub identity.

---

## 1. Manual Configuration Steps

To fully activate the automation in your repository fork, complete the following steps:

### Step A: Register the GitHub Account & Generate a PAT
1. **Register the Account:** Create the GitHub account `clnsmth-ai-agent` (or configure your existing machine/bot user).
2. **Generate a Personal Access Token (PAT):**
   * Log in to the bot account on GitHub.
   * Go to **Settings > Developer Settings > Personal Access Tokens**.
   * We recommend using a **Fine-Grained Personal Access Token** scoped to your fork repository with the following repository permissions:
     * **Contents:** Read & Write (to commit and push changes)
     * **Issues:** Read & Write (to view, label, and comment on issues)
     * **Pull Requests:** Read & Write (to create, update, review, and comment on PRs)
     * **Workflows:** Read & Write (to trigger actions and check workflow runs)

### Step B: Configure Repository Secrets
In your fork repository on GitHub, navigate to **Settings > Secrets and variables > Actions** and add two **Repository Secrets**:
1. `GEMINI_API_KEY`: Your Google Gemini API Key.
2. `PAT_FOR_PR`: The PAT generated in **Step A** for the `clnsmth-ai-agent` account.

> [!IMPORTANT]
> The workflow uses `secrets.PAT_FOR_PR` instead of the standard `GITHUB_TOKEN` to ensure that commits and PRs created by the agent can trigger subsequent workflow runs (like CI, ODK tests, and code reviews).

### Step C: Restrict Controller Access
Verify that only authorized GitHub users can trigger the agent.
1. Open the file `.github/ai-controllers.json`.
2. Confirm it restricts access as desired during this bootstrap phase:
   ```json
   [
     "clnsmth"
   ]
   ```

### Step D: Push and Merge the Refactor Branch
1. Push your local `refactor-gemini` branch to your GitHub fork:
   ```bash
   git push origin refactor-gemini
   ```
2. Open a Pull Request on GitHub to merge `refactor-gemini` into your main/master branch.
3. Merge the PR. (Since GitHub issue/PR event-triggers default to the main branch workflows, the `ai-agent.yml` workflow needs to be on the default branch to listen to mentions properly).

---

## 2. Verification & Testing Plan

Once the configuration steps are complete, execute these three manual test cases to verify functionality.

### Test Case 1: Manual Workflow Dispatch (Smoke Test)
This tests the connection between the runner, the PAT, and the Gemini API without needing to parse issue comments.

1. Navigate to the **Actions** tab of your repository on GitHub.
2. Select the **AI Agent GitHub Mentions** workflow from the left sidebar.
3. Click the **Run workflow** dropdown on the right:
   * **Use workflow from:** Choose `main` or your default branch.
   * **Issue or PR number to respond to:** Enter any open issue number (e.g., `1`).
   * **Type of item:** Select `issue`.
   * **The request/prompt for the agent:** Enter `quick question: hello! Are you online?`
4. Click **Run workflow**.
5. **Expected Outcome:**
   * The workflow starts and is named after your run.
   * The agent posts a comment on the specified issue with a status update, answers the question, and appends the standard `@clnsmth-ai-agent` signature block.

---

### Test Case 2: Triggering via Issue Comment Mention
This verifies that the GitHub comment listener parses the custom `@clnsmth-ai-agent please` trigger correctly.

1. Open or create a test issue on your repository.
2. Post a comment on the issue with the trigger phrase:
   ```markdown
   @clnsmth-ai-agent please quick question: what is the active git branch name?
   ```
   *(We include `quick question` here to bypass the heavy ODK container load and get a fast response).*
3. **Expected Outcome:**
   * Within a minute, the workflow is triggered on GitHub Actions.
   * The agent reacts to your comment with a 👀 (`eyes`) reaction.
   * The agent comments back: `🤖 Working on it... Follow along: [View workflow run](url)`.
   * When complete, the agent replies with the command output and signature block.

---

### Test Case 3: Complete Ontology Branch & PR Creation
This tests the full agent capability, including checking out terms, verifying them, pushing, and creating a PR.

1. Open an issue on your repository to edit/create a term. For example:
   > Title: Edit term UBERON:0001742
   > Body: @clnsmth-ai-agent please update the definition of epiglottic cartilage to match the text in GEMINI.md.
2. **Expected Outcome:**
   * The agent reacts with 👀 and posts a `Working on it...` message.
   * The workflow runs in the ODK container (`obolibrary/odkfull`).
   * The agent:
     1. Creates a new branch named `clnsmth-ai-agent-issue-<number>-run1`.
     2. Checks out the term via `obo-checkout.pl`.
     3. Makes the requested modifications.
     4. Checks the term back in via `obo-checkin.pl`.
     5. Reserializes the edit file using `robot convert`.
     6. Commits and signs off with `@clnsmth-ai-agent`.
     7. Pushes the branch and creates a Pull Request targeting your fork using `gh pr create --repo <owner/repo>`.
   * The agent leaves a comment on the original issue referencing the new PR.

---

## 3. Troubleshooting Quick Reference

| Symptom | Probable Cause | Action |
| :--- | :--- | :--- |
| **Workflow doesn't trigger on comments** | Trigger format error, unauthorized user, or workflow not on default branch. | Verify you are posting as `clnsmth` (or a username in `ai-controllers.json`) and using `@clnsmth-ai-agent please`. Ensure `ai-agent.yml` is merged into the default branch. |
| **Eyes reaction added but agent doesn't reply** | `PAT_FOR_PR` has insufficient permissions to comment/write. | Verify PAT permissions in Developer Settings for the `clnsmth-ai-agent` account. |
| **Workflow fails on "Run Gemini CLI" step** | Missing or incorrect `GEMINI_API_KEY`. | Check repository secrets and verify the API key is active. |
| **Commit/PR fails to trigger CI** | Workflow triggered with default `GITHUB_TOKEN` instead of a personal PAT. | Ensure `PAT_FOR_PR` is configured as a secret and successfully loaded in the checkout step. |
