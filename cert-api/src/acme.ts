/**
 * ACME client for Let's Encrypt certificate issuance.
 * Implements RFC 8555 with DNS-01 challenge validation.
 */

import { CloudflareDns } from "./dns";

interface AcmeDirectory {
  newNonce: string;
  newAccount: string;
  newOrder: string;
}

interface AcmeOrder {
  status: string;
  authorizations: string[];
  finalize: string;
  certificate?: string;
}

interface AcmeAuthorization {
  status: string;
  identifier: { type: string; value: string };
  challenges: AcmeChallenge[];
}

interface AcmeChallenge {
  type: string;
  status: string;
  url: string;
  token: string;
}

interface JwkPublic {
  kty: string;
  crv: string;
  x: string;
  y: string;
}

export interface CertificateBundle {
  cert: string;
  key: string;
  domain: string;
  expires_at: string;
  issued_at: string;
}

export class AcmeClient {
  private directoryUrl: string;
  private directory: AcmeDirectory | null = null;
  private accountUrl: string | null = null;
  private privateKey: CryptoKey | null = null;
  private publicJwk: JwkPublic | null = null;
  private dns: CloudflareDns;

  constructor(directoryUrl: string, dns: CloudflareDns) {
    this.directoryUrl = directoryUrl;
    this.dns = dns;
  }

  /**
   * Initialize with an existing account key or generate a new one.
   */
  async init(accountKeyJwk?: JsonWebKey): Promise<JsonWebKey> {
    if (accountKeyJwk) {
      this.privateKey = await crypto.subtle.importKey(
        "jwk",
        accountKeyJwk,
        { name: "ECDSA", namedCurve: "P-256" },
        true,
        ["sign"]
      );
    } else {
      const keyPair = await crypto.subtle.generateKey(
        { name: "ECDSA", namedCurve: "P-256" },
        true,
        ["sign"]
      );
      this.privateKey = keyPair.privateKey;
    }

    const exportedPrivate = await crypto.subtle.exportKey("jwk", this.privateKey);
    this.publicJwk = {
      kty: exportedPrivate.kty!,
      crv: exportedPrivate.crv!,
      x: exportedPrivate.x!,
      y: exportedPrivate.y!,
    };

    await this.fetchDirectory();
    return exportedPrivate;
  }

  private async fetchDirectory(): Promise<void> {
    const response = await fetch(this.directoryUrl);
    this.directory = (await response.json()) as AcmeDirectory;
  }

  private async getNonce(): Promise<string> {
    const response = await fetch(this.directory!.newNonce, { method: "HEAD" });
    return response.headers.get("Replay-Nonce")!;
  }

  private base64url(data: ArrayBuffer | Uint8Array | string): string {
    let bytes: Uint8Array;
    if (typeof data === "string") {
      bytes = new TextEncoder().encode(data);
    } else if (data instanceof ArrayBuffer) {
      bytes = new Uint8Array(data);
    } else {
      bytes = data;
    }

    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
  }

  private async signPayload(
    url: string,
    payload: unknown,
    useJwk: boolean = false
  ): Promise<string> {
    const nonce = await this.getNonce();

    const protectedHeader: Record<string, unknown> = {
      alg: "ES256",
      nonce,
      url,
    };

    if (useJwk) {
      protectedHeader.jwk = this.publicJwk;
    } else {
      protectedHeader.kid = this.accountUrl;
    }

    const protectedB64 = this.base64url(JSON.stringify(protectedHeader));
    const payloadB64 = payload === "" ? "" : this.base64url(JSON.stringify(payload));

    const signingInput = `${protectedB64}.${payloadB64}`;
    const signature = await crypto.subtle.sign(
      { name: "ECDSA", hash: "SHA-256" },
      this.privateKey!,
      new TextEncoder().encode(signingInput)
    );

    // Convert DER signature to raw format for JWS
    const sigBytes = new Uint8Array(signature);
    const r = sigBytes.slice(0, 32);
    const s = sigBytes.slice(32, 64);
    const rawSig = new Uint8Array(64);
    rawSig.set(r, 0);
    rawSig.set(s, 32);

    return JSON.stringify({
      protected: protectedB64,
      payload: payloadB64,
      signature: this.base64url(rawSig),
    });
  }

  private async acmeRequest(
    url: string,
    payload: unknown,
    useJwk: boolean = false
  ): Promise<{ body: unknown; headers: Headers }> {
    const body = await this.signPayload(url, payload, useJwk);
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/jose+json" },
      body,
    });

    const responseBody = await response.json();

    if (!response.ok) {
      const error = responseBody as { type?: string; detail?: string };
      throw new Error(`ACME error: ${error.type} - ${error.detail}`);
    }

    return { body: responseBody, headers: response.headers };
  }

  /**
   * Register or fetch existing ACME account.
   */
  async registerAccount(email?: string): Promise<void> {
    const payload: Record<string, unknown> = {
      termsOfServiceAgreed: true,
    };
    if (email) {
      payload.contact = [`mailto:${email}`];
    }

    const { headers } = await this.acmeRequest(this.directory!.newAccount, payload, true);
    this.accountUrl = headers.get("Location");
  }

  /**
   * Request a certificate for a domain using DNS-01 challenge.
   */
  async requestCertificate(domain: string): Promise<CertificateBundle> {
    // Create order
    const { body: order, headers: orderHeaders } = await this.acmeRequest(
      this.directory!.newOrder,
      { identifiers: [{ type: "dns", value: domain }] }
    );
    const orderUrl = orderHeaders.get("Location")!;
    const orderData = order as AcmeOrder;

    // Get authorization
    const authResponse = await fetch(orderData.authorizations[0]);
    const auth = (await authResponse.json()) as AcmeAuthorization;

    // Find DNS-01 challenge
    const dnsChallenge = auth.challenges.find((c) => c.type === "dns-01");
    if (!dnsChallenge) {
      throw new Error("No DNS-01 challenge found");
    }

    // Compute challenge response
    const thumbprint = await this.computeThumbprint();
    const keyAuth = `${dnsChallenge.token}.${thumbprint}`;
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(keyAuth));
    const txtValue = this.base64url(digest);

    // Create DNS TXT record
    const challengeName = `_acme-challenge.${domain}`;
    await this.dns.cleanupAcmeRecords(domain);
    const recordId = await this.dns.createTxtRecord(challengeName, txtValue);

    try {
      // Wait for DNS propagation
      await this.sleep(5000);

      // Respond to challenge
      await this.acmeRequest(dnsChallenge.url, {});

      // Poll for authorization completion
      await this.pollAuthorization(orderData.authorizations[0]);

      // Generate CSR
      const { privateKey: certKey, csr } = await this.generateCsr(domain);

      // Finalize order
      await this.acmeRequest(orderData.finalize, { csr });

      // Poll for certificate
      const certUrl = await this.pollOrder(orderUrl);

      // Download certificate
      const certResponse = await fetch(certUrl, {
        headers: { Accept: "application/pem-certificate-chain" },
      });
      const cert = await certResponse.text();

      // Export private key to PEM
      const keyPem = await this.keyToPem(certKey);

      // Calculate expiry (Let's Encrypt certs are valid for 90 days)
      const now = new Date();
      const expires = new Date(now.getTime() + 90 * 24 * 60 * 60 * 1000);

      return {
        cert,
        key: keyPem,
        domain,
        issued_at: now.toISOString(),
        expires_at: expires.toISOString(),
      };
    } finally {
      // Clean up DNS record
      await this.dns.deleteRecord(recordId);
    }
  }

  private async computeThumbprint(): Promise<string> {
    const jwkOrdered = JSON.stringify({
      crv: this.publicJwk!.crv,
      kty: this.publicJwk!.kty,
      x: this.publicJwk!.x,
      y: this.publicJwk!.y,
    });
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(jwkOrdered));
    return this.base64url(digest);
  }

  private async pollAuthorization(url: string, maxAttempts: number = 30): Promise<void> {
    for (let i = 0; i < maxAttempts; i++) {
      const response = await fetch(url);
      const auth = (await response.json()) as AcmeAuthorization;

      if (auth.status === "valid") {
        return;
      }
      if (auth.status === "invalid") {
        throw new Error("Authorization failed");
      }

      await this.sleep(2000);
    }
    throw new Error("Authorization timeout");
  }

  private async pollOrder(url: string, maxAttempts: number = 30): Promise<string> {
    for (let i = 0; i < maxAttempts; i++) {
      const response = await fetch(url);
      const order = (await response.json()) as AcmeOrder;

      if (order.status === "valid" && order.certificate) {
        return order.certificate;
      }
      if (order.status === "invalid") {
        throw new Error("Order failed");
      }

      await this.sleep(2000);
    }
    throw new Error("Order timeout");
  }

  private async generateCsr(domain: string): Promise<{ privateKey: CryptoKey; csr: string }> {
    const keyPair = await crypto.subtle.generateKey(
      { name: "ECDSA", namedCurve: "P-256" },
      true,
      ["sign"]
    );

    // Build CSR ASN.1 structure
    const csrInfo = this.buildCsrInfo(domain, keyPair.publicKey);
    const csrInfoDer = await this.encodeCsrInfo(csrInfo, keyPair.publicKey);

    // Sign CSR
    const signature = await crypto.subtle.sign(
      { name: "ECDSA", hash: "SHA-256" },
      keyPair.privateKey,
      csrInfoDer
    );

    // Build complete CSR
    const csr = this.buildCsr(csrInfoDer, signature);

    return {
      privateKey: keyPair.privateKey,
      csr: this.base64url(csr),
    };
  }

  private buildCsrInfo(domain: string, _publicKey: CryptoKey): Uint8Array {
    // Build Subject Name: SEQUENCE { SET { SEQUENCE { OID, UTF8String } } }
    const domainBytes = new TextEncoder().encode(domain);

    // Calculate lengths from inside out:
    // - UTF8String: tag(1) + len(1) + content(n) = 2 + n
    // - Inner SEQUENCE content: OID(5) + UTF8String(2+n) = 7 + n
    // - Inner SEQUENCE: tag(1) + len(1) + content(7+n) = 9 + n
    // - SET content: Inner SEQUENCE(9+n) = 9 + n
    // - SET: tag(1) + len(1) + content(9+n) = 11 + n
    // - Outer SEQUENCE content: SET(11+n) = 11 + n
    // - Outer SEQUENCE: tag(1) + len(1) + content(11+n) = 13 + n

    const n = domainBytes.length;
    const cn = new Uint8Array([
      0x30, n + 11,  // Outer SEQUENCE (contains SET)
      0x31, n + 9,   // SET (contains inner SEQUENCE)
      0x30, n + 7,   // Inner SEQUENCE (contains OID + UTF8String)
      0x06, 0x03, 0x55, 0x04, 0x03,  // OID for CN (2.5.4.3)
      0x0c, n,       // UTF8String tag + length
      ...domainBytes,
    ]);

    return cn;
  }

  private async encodeCsrInfo(subject: Uint8Array, publicKey: CryptoKey): Promise<Uint8Array> {
    const pubKeyJwk = await crypto.subtle.exportKey("jwk", publicKey);
    const x = this.base64urlDecode(pubKeyJwk.x!);
    const y = this.base64urlDecode(pubKeyJwk.y!);

    // EC public key in uncompressed form
    const pubKeyBytes = new Uint8Array(65);
    pubKeyBytes[0] = 0x04;
    pubKeyBytes.set(x, 1);
    pubKeyBytes.set(y, 33);

    // Build SubjectPublicKeyInfo for P-256 (fixed size, so hardcoded lengths are OK)
    const spki = new Uint8Array([
      0x30, 0x59, // SEQUENCE (89 bytes)
      0x30, 0x13, // AlgorithmIdentifier SEQUENCE (19 bytes)
      0x06, 0x07, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02, 0x01, // ecPublicKey OID
      0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03, 0x01, 0x07, // P-256 OID
      0x03, 0x42, 0x00, // BIT STRING (66 bytes, 0 unused bits)
      ...pubKeyBytes,
    ]);

    // Build CertificationRequestInfo
    const version = new Uint8Array([0x02, 0x01, 0x00]); // INTEGER 0
    const attributes = new Uint8Array([0xa0, 0x00]); // Empty attributes

    // Concatenate all parts
    const content = new Uint8Array(
      version.length + subject.length + spki.length + attributes.length
    );
    let offset = 0;
    content.set(version, offset);
    offset += version.length;
    content.set(subject, offset);
    offset += subject.length;
    content.set(spki, offset);
    offset += spki.length;
    content.set(attributes, offset);

    // Wrap in SEQUENCE with proper length encoding
    return this.derSequence(content);
  }

  /**
   * Encode ASN.1 DER length properly (no superfluous leading zeros).
   */
  private derLength(len: number): Uint8Array {
    if (len < 128) {
      return new Uint8Array([len]);
    } else if (len < 256) {
      return new Uint8Array([0x81, len]);
    } else {
      return new Uint8Array([0x82, (len >> 8) & 0xff, len & 0xff]);
    }
  }

  /**
   * Wrap content in an ASN.1 SEQUENCE.
   */
  private derSequence(content: Uint8Array): Uint8Array {
    const lenBytes = this.derLength(content.length);
    const result = new Uint8Array(1 + lenBytes.length + content.length);
    result[0] = 0x30; // SEQUENCE tag
    result.set(lenBytes, 1);
    result.set(content, 1 + lenBytes.length);
    return result;
  }

  /**
   * Wrap content in an ASN.1 BIT STRING.
   */
  private derBitString(content: Uint8Array): Uint8Array {
    const lenBytes = this.derLength(content.length + 1);
    const result = new Uint8Array(1 + lenBytes.length + 1 + content.length);
    result[0] = 0x03; // BIT STRING tag
    result.set(lenBytes, 1);
    result[1 + lenBytes.length] = 0x00; // No unused bits
    result.set(content, 1 + lenBytes.length + 1);
    return result;
  }

  /**
   * Encode an integer for DER (handles leading zeros and sign bit).
   */
  private derInteger(value: Uint8Array): Uint8Array {
    // Remove leading zeros (but keep at least one byte)
    let start = 0;
    while (start < value.length - 1 && value[start] === 0) {
      start++;
    }
    const trimmed = value.slice(start);

    // Add leading 0x00 if high bit is set (to keep it positive)
    const needsPadding = trimmed[0] & 0x80;
    const content = needsPadding
      ? new Uint8Array([0x00, ...trimmed])
      : trimmed;

    const lenBytes = this.derLength(content.length);
    const result = new Uint8Array(1 + lenBytes.length + content.length);
    result[0] = 0x02; // INTEGER tag
    result.set(lenBytes, 1);
    result.set(content, 1 + lenBytes.length);
    return result;
  }

  /**
   * Convert IEEE P1363 signature (r||s) to DER format SEQUENCE { INTEGER r, INTEGER s }.
   */
  private signatureToDer(sig: Uint8Array): Uint8Array {
    const r = sig.slice(0, 32);
    const s = sig.slice(32, 64);

    const derR = this.derInteger(r);
    const derS = this.derInteger(s);

    const content = new Uint8Array(derR.length + derS.length);
    content.set(derR, 0);
    content.set(derS, derR.length);

    return this.derSequence(content);
  }

  private buildCsr(csrInfo: Uint8Array, signature: ArrayBuffer): Uint8Array {
    const sigBytes = new Uint8Array(signature);

    // Signature algorithm: ecdsa-with-SHA256
    const sigAlg = new Uint8Array([
      0x30, 0x0a, 0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x04, 0x03, 0x02,
    ]);

    // Convert signature from IEEE P1363 (r||s) to DER format
    const derSig = this.signatureToDer(sigBytes);

    // BIT STRING for signature
    const sigBitString = this.derBitString(derSig);

    // Concatenate all parts
    const content = new Uint8Array(csrInfo.length + sigAlg.length + sigBitString.length);
    let offset = 0;
    content.set(csrInfo, offset);
    offset += csrInfo.length;
    content.set(sigAlg, offset);
    offset += sigAlg.length;
    content.set(sigBitString, offset);

    // Wrap in outer SEQUENCE
    return this.derSequence(content);
  }

  private base64urlDecode(str: string): Uint8Array {
    const base64 = str.replace(/-/g, "+").replace(/_/g, "/");
    const padding = "=".repeat((4 - (base64.length % 4)) % 4);
    const binary = atob(base64 + padding);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  private async keyToPem(privateKey: CryptoKey): Promise<string> {
    // Use WebCrypto to export PKCS#8 directly - much simpler than manual ASN.1
    const pkcs8 = await crypto.subtle.exportKey("pkcs8", privateKey);
    const bytes = new Uint8Array(pkcs8);

    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    const base64 = btoa(binary);
    const lines = base64.match(/.{1,64}/g) || [];
    return `-----BEGIN PRIVATE KEY-----\n${lines.join("\n")}\n-----END PRIVATE KEY-----`;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
