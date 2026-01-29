/**
 * Cloudflare DNS API helper for ACME DNS-01 challenge validation.
 */

export interface DnsRecord {
  id: string;
  name: string;
  type: string;
  content: string;
}

export class CloudflareDns {
  private apiToken: string;
  private zoneId: string;

  constructor(apiToken: string, zoneId: string) {
    this.apiToken = apiToken;
    this.zoneId = zoneId;
  }

  private async request(
    endpoint: string,
    method: string = "GET",
    body?: unknown
  ): Promise<unknown> {
    const url = `https://api.cloudflare.com/client/v4/zones/${this.zoneId}${endpoint}`;
    const response = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${this.apiToken}`,
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    const text = await response.text();
    let data: {
      success: boolean;
      errors?: Array<{ message: string }>;
      result?: unknown;
    };
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`Cloudflare API response not JSON (${response.status}): ${text.slice(0, 200)}`);
    }

    if (!data.success) {
      const errors = data.errors?.map((e) => e.message).join(", ") || "Unknown error";
      throw new Error(`Cloudflare API error: ${errors}`);
    }

    return data.result;
  }

  /**
   * Create a TXT record for ACME DNS-01 challenge.
   */
  async createTxtRecord(name: string, content: string): Promise<string> {
    const result = (await this.request("/dns_records", "POST", {
      type: "TXT",
      name,
      content,
      ttl: 60,
    })) as DnsRecord;
    return result.id;
  }

  /**
   * Delete a DNS record by ID.
   */
  async deleteRecord(recordId: string): Promise<void> {
    await this.request(`/dns_records/${recordId}`, "DELETE");
  }

  /**
   * Find TXT records by name.
   */
  async findTxtRecords(name: string): Promise<DnsRecord[]> {
    const result = (await this.request(
      `/dns_records?type=TXT&name=${encodeURIComponent(name)}`
    )) as DnsRecord[];
    return result;
  }

  /**
   * Clean up any existing ACME challenge records for a domain.
   */
  async cleanupAcmeRecords(domain: string): Promise<void> {
    const challengeName = `_acme-challenge.${domain}`;
    const records = await this.findTxtRecords(challengeName);
    for (const record of records) {
      await this.deleteRecord(record.id);
    }
  }
}
