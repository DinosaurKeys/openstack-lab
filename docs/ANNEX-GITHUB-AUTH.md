# Annex: GitHub authentication and Git push setup

This annex records the authentication workflow used to let this management machine push changes to the `DinosaurKeys/openstack-lab` repository. It is intended as a reminder and recovery guide.

## What was configured

- An Ed25519 SSH key was available at `~/.ssh/id_ed25519` (public key: `~/.ssh/id_ed25519.pub`).
- The matching public key had been added to the GitHub account `DinosaurKeys`.
- SSH authentication to GitHub succeeded, so Git can push over SSH without a GitHub password or personal access token.
- The repository remote is `git@github.com:DinosaurKeys/openstack-lab.git`.

The private key must stay on this machine. Never paste it into chat, commit it, or copy it into this repository. The `.pub` public key is the part that is registered with GitHub.

## Verify the existing setup

Run these commands from the repository:

```bash
ssh -T -o BatchMode=yes -o ConnectTimeout=5 git@github.com
git remote -v
git ls-remote origin refs/heads/main
git status --short --branch
```

A successful SSH test prints a greeting for `DinosaurKeys` and says GitHub does not provide shell access. That message is expected: GitHub accepts SSH for Git operations, not an interactive shell.

The remote should be:

```text
git@github.com:DinosaurKeys/openstack-lab.git
```

If the remote is HTTPS and SSH authentication works, switch only this repository's remote (not global Git configuration):

```bash
git remote set-url origin git@github.com:DinosaurKeys/openstack-lab.git
git remote -v
```

## Commit and push safely

Set a commit identity for this repository if Git asks for one. This changes local Git metadata only; it does not authenticate to GitHub:

```bash
git config user.name "Your Name"
git config user.email "your-github-noreply-address"
```

Then review, commit, and push:

```bash
git status --short
git diff --check
git diff

git add <reviewed-files>
git commit -m "Describe the change"
GIT_TERMINAL_PROMPT=0 git push origin main
```

Verify the remote branch after pushing:

```bash
git ls-remote origin refs/heads/main
git status --short --branch
```

The commit hash reported by `git ls-remote` should match the pushed commit, and the branch should no longer be ahead of `origin/main`.

## If SSH authentication fails

1. Confirm the key files exist without printing the private key:

   ```bash
   test -f ~/.ssh/id_ed25519 && echo "private key exists"
   test -f ~/.ssh/id_ed25519.pub && echo "public key exists"
   ```

2. Check the GitHub SSH handshake:

   ```bash
   ssh -T -o BatchMode=yes -o ConnectTimeout=5 git@github.com
   ```

3. If the public key is not registered to the correct GitHub account, add the contents of `~/.ssh/id_ed25519.pub` under GitHub Settings → SSH and GPG keys. Only display/copy the `.pub` file. Never display or share `~/.ssh/id_ed25519`.

4. Retry `ssh -T ...`, then verify the repository remote and run `git ls-remote` before pushing.

If the private key is missing, do not overwrite or regenerate keys casually: first check for a backup or another configured key. If a new key is needed, create it locally and register only its public half with GitHub.

## Important distinction: SSH versus GitHub CLI

This repository workflow uses SSH for `git push`. It does not require the `gh` command-line program. SSH Git access also does not automatically authorize GitHub API operations such as editing repository descriptions or topics; those require a separately authorized API client/token. Do not put tokens in a remote URL, shell history, or this repository.

## Secret and privacy rules

- Never commit or share the private key (`~/.ssh/id_ed25519`).
- Never add passwords, personal access tokens, MFA codes, or private key contents to inventory, documentation, or command output.
- Do not enable plaintext Git credential storage as a shortcut.
- Do not copy this machine's private address or other local environment details into public docs unless they are deliberately part of the lab's documented topology.
