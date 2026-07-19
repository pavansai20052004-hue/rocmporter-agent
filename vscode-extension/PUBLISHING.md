# Publishing ROCmPorter to the VS Code Marketplace

Everything is packaged and ready — publishing is a one-time 10-minute setup,
then a single command per release.

## One-time setup (needs the repo owner)

1. **Create a publisher** at https://marketplace.visualstudio.com/manage
   - Sign in with any Microsoft account (create one free if needed).
   - Click **Create publisher** → ID: `rocmporter` (must match `publisher` in
     package.json — if `rocmporter` is taken, pick another and update
     package.json to match).
2. **Create a Personal Access Token** at https://dev.azure.com
   - Profile icon → *Personal access tokens* → *New token*
   - Organization: **All accessible organizations**
   - Scopes: *Custom defined* → **Marketplace → Manage**
   - Copy the token (shown once).

## Publish (each release)

```bash
cd vscode-extension
npx @vscode/vsce login rocmporter    # paste the PAT once
npx @vscode/vsce publish             # publishes the current version
```

Bump `"version"` in package.json before each new release
(`npx vsce publish patch` bumps + publishes in one step).

## What's already done

- ✅ `rocmporter-0.1.0.vsix` builds clean (`npx @vscode/vsce package`)
- ✅ icon.png, gallery banner, categories, keywords, repository/homepage/bugs links
- ✅ MIT LICENSE bundled
- ✅ README.md doubles as the Marketplace listing page
