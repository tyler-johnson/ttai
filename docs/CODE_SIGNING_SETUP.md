# Apple Code Signing & Notarization Setup

This guide walks through setting up code signing and notarization for TTAI macOS builds. Once configured, users can download and run the app without Gatekeeper warnings or quarantine issues.

## Prerequisites

- Apple Developer Program membership ($99/year)
- Xcode installed (for certificate management)
- Access to your repository's GitHub secrets

## Part 1: Developer ID Certificate

### Create a Developer ID Certificate (if you don't have one)

1. Go to [Apple Developer Certificates](https://developer.apple.com/account/resources/certificates/list)
2. Click the "+" button to create a new certificate
3. Select **Developer ID Application** (not "Developer ID Installer")
4. Follow the Certificate Signing Request (CSR) process:
   - Open Keychain Access on your Mac
   - Go to Keychain Access > Certificate Assistant > Request a Certificate From a Certificate Authority
   - Enter your email, select "Saved to disk", and save the CSR file
   - Upload the CSR to Apple's portal
5. Download the certificate and double-click to install in Keychain

### Export Certificate from Keychain

1. Open **Keychain Access** on your Mac
2. In the sidebar, select **login** keychain and **My Certificates** category
3. Find your certificate named "Developer ID Application: Your Name (TEAMID)"
   - Make sure you see the disclosure triangle with a private key inside
4. Right-click the certificate and select **Export...**
5. Save as a `.p12` file with a strong password
   - Remember this password - you'll need it for GitHub secrets

### Convert to Base64

```bash
base64 -i Certificates.p12 | pbcopy
```

This copies the base64-encoded certificate to your clipboard.

### Find Your Team ID and Team Name

```bash
security find-identity -v -p codesigning | grep "Developer ID"
```

Look for output like:
```
1) ABC1234DEF "Developer ID Application: Your Name (ABC1234DEF)"
```

- **Team ID**: The 10-character code in parentheses (e.g., `ABC1234DEF`)
- **Team Name**: The full name including your name (e.g., `Your Name (ABC1234DEF)`)

## Part 2: App Store Connect API Key

The API key is used for notarization (submitting your app to Apple for verification).

### Create an API Key

1. Go to [App Store Connect API Keys](https://appstoreconnect.apple.com/access/integrations/api)
2. Click the "+" button to generate a new key
3. Configure the key:
   - **Name**: `TTAI CI Notarization` (or similar)
   - **Access**: Select **Developer** role
4. Click **Generate**
5. **Important**: Download the `.p8` file immediately - it's only available once!
6. Note the **Key ID** and **Issuer ID** shown on the page

### Convert API Key to Base64

```bash
base64 -i AuthKey_XXXXXXXXXX.p8 | pbcopy
```

This copies the base64-encoded API key to your clipboard.

## Part 3: GitHub Secrets

Add the following secrets to your repository:

1. Go to your repository on GitHub
2. Navigate to **Settings** > **Secrets and variables** > **Actions**
3. Add each secret using **New repository secret**

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `APPLE_CERTIFICATE_BASE64` | Base64-encoded .p12 certificate | (long base64 string) |
| `APPLE_CERTIFICATE_PASSWORD` | Password for the .p12 file | (your password) |
| `KEYCHAIN_PASSWORD` | Temporary keychain password | (any random string) |
| `APPLE_TEAM_NAME` | Full team name for signing identity | `Your Name (ABC1234DEF)` |
| `APPLE_API_KEY_ID` | App Store Connect API Key ID | `XXXXXXXXXX` |
| `APPLE_API_ISSUER_ID` | App Store Connect Issuer ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `APPLE_API_KEY_BASE64` | Base64-encoded .p8 API key | (long base64 string) |

## Part 4: Local Testing

You can test code signing locally before pushing to CI.

### Test Signing

```bash
# Set your signing identity
export CODESIGN_IDENTITY="Developer ID Application: Your Name (ABC1234DEF)"

# Build and sign
cd src-go
make clean && make zip-darwin-arm64

# Verify the signature
codesign -dv --verbose=4 dist/TTAI-darwin-arm64.app
```

Expected output includes:
```
Authority=Developer ID Application: Your Name (ABC1234DEF)
Authority=Developer ID Certification Authority
Authority=Apple Root CA
```

### Test Notarization (Optional)

```bash
# Submit for notarization
xcrun notarytool submit dist/TTAI-darwin-arm64.zip \
  --key ~/path/to/AuthKey_XXXXXXXXXX.p8 \
  --key-id "XXXXXXXXXX" \
  --issuer "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
  --wait

# Staple the notarization ticket
xcrun stapler staple dist/TTAI-darwin-arm64.app

# Re-zip for distribution
cd dist
rm TTAI-darwin-arm64.zip
ditto -c -k --keepParent TTAI-darwin-arm64.app TTAI-darwin-arm64.zip
```

### Verify Gatekeeper Approval

```bash
spctl -a -t exec -vv dist/TTAI-darwin-arm64.app
```

Expected output:
```
dist/TTAI-darwin-arm64.app: accepted
source=Notarized Developer ID
```

## Troubleshooting

### "The specified item could not be found in the keychain"

The certificate wasn't imported correctly. Make sure:
- You exported both the certificate AND private key (look for the disclosure triangle)
- The .p12 password is correct in GitHub secrets

### Notarization fails with "Invalid signature"

- Ensure the app was signed with `--options runtime` (hardened runtime)
- Check that entitlements.plist exists and is valid

### Notarization fails with "The software is not signed"

- The `CODESIGN_IDENTITY` secret may be empty or incorrect
- Verify the team name format matches exactly: `Your Name (TEAMID)`

### "spctl" shows "rejected"

- The app may not be notarized yet
- Run `xcrun stapler staple` after notarization completes
- Check the notarization log: `xcrun notarytool log <submission-id> --key ...`

## How It Works

The GitHub Actions workflow:

1. **Imports the certificate** into a temporary keychain on the macOS runner
2. **Signs the app** using the Makefile's `sign-darwin-*` targets with hardened runtime
3. **Submits to Apple** for notarization and waits for approval
4. **Staples the ticket** to the app bundle so it works offline
5. **Re-zips** the stapled app for distribution
6. **Cleans up** the keychain and credentials

When users download the release:
- macOS verifies the signature and notarization ticket
- No quarantine warnings or "unidentified developer" dialogs
- App opens immediately on first launch

## Security Notes

- The .p12 certificate contains your private key - keep it secure
- GitHub secrets are encrypted and only exposed during workflow runs
- The temporary keychain is deleted after each build
- Never commit certificates or API keys to the repository
