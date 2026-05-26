# Updating Hermes Dashboard

Hermes Dashboard can be updated several ways. Use the path that matches your comfort level and install style.

## From inside the dashboard

1. Open the dashboard in your browser.
2. Click the gear button in the top-right header.
3. Click **Update Instructions**.
4. Choose one of the update paths shown there.
5. After updating files, restart the dashboard process or service.
6. Reopen the gear menu and click **Reload Dashboard** to clear browser cache.

The in-dashboard button intentionally shows instructions instead of silently running updates. Updating files can overwrite local changes, require service restarts, or need credentials, so the user should stay in control.

## GitHub Desktop or another Git GUI

1. Open the `hermesdashboard` repository in GitHub Desktop, VS Code Source Control, Fork, Tower, or another Git GUI.
2. Fetch origin.
3. Pull the latest `main` branch.
4. Restart the dashboard launcher or service.
5. Use **Reload Dashboard** in the dashboard gear menu.

## Download ZIP from GitHub

1. Open <https://github.com/mojomast/hermesdashboard>.
2. Click **Code → Download ZIP**.
3. Extract the ZIP.
4. Copy the new files over your existing dashboard install directory.
5. Preserve local files such as `.env.local`, generated launcher scripts, local databases, and logs.
6. Restart the dashboard and reload the browser.

This path is useful for users who do not want to use Git directly.

## Re-run the installer

If you originally used the one-line installer, you can re-run it. The installer is designed to clone or update the dashboard checkout, then regenerate launchers when needed.

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/mojomast/hermesdashboard/main/install.sh)"
```

## Terminal update

From the dashboard install directory:

```sh
git pull --ff-only
python -m pip install -r requirements.txt
```

Then restart the dashboard process/service and hard-refresh the browser.

## If you have local changes

If Git says local files would be overwritten:

1. Back up your local changes.
2. Commit, stash, or move them aside.
3. Pull the update.
4. Reapply only the changes you still need.

Do not delete `.env.local` or your generated launcher scripts unless you plan to re-run setup.
