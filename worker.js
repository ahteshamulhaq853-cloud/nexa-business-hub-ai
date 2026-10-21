
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    const headers = {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*"
    };

    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          ...headers,
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type"
        }
      });
    }

    if (url.pathname === "/api/health") {
      return Response.json({
        status: "ok",
        aiConfigured: Boolean(env.AI)
      }, { headers });
    }

    if (url.pathname === "/api/generate" && request.method === "POST") {
      try {
        const body = await request.json();
        const service = String(body.service || "").slice(0, 150).trim();
        const details = String(body.details || "").slice(0, 6000).trim();
        const language = String(body.language || "Urdu").slice(0, 30);

        if (!service || !details) {
          return Response.json({
            error: "براہِ کرم سروس اور تفصیلات درج کریں۔"
          }, { status: 400, headers });
        }

        if (!env.AI) {
          return Response.json({
            error: "AI binding موجود نہیں۔ Cloudflare کی سیٹنگ چیک کریں۔"
          }, { status: 503, headers });
        }

        const result = await env.AI.run(
          "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
          {
            messages: [
              {
                role: "system",
                content: `You are Nexa Business Hub AI, a professional business assistant.

Respond in the language requested by the user. For Urdu, use natural, readable Urdu script.

Make answers useful, complete, organized, and easy to read. Use clear headings, short paragraphs, numbered steps, and bullet points.

For business plans, include:
1. Business overview and goals.
2. Services and target customers.
3. Startup costs in Pakistani rupees when relevant.
4. Monthly expenses, including rent, electricity, internet, supplies and maintenance when applicable.
5. Possible income and profit estimates, clearly marked as estimates with assumptions.
6. Marketing strategies.
7. Practical steps to get started.
8. Risks and ways to reduce them.
9. A concise conclusion.

Do not invent exact market prices. Label uncertain amounts as estimates and advise checking local prices. Show calculations where useful. Finish the answer with a clear conclusion; do not end mid-sentence. If information is missing, state reasonable assumptions.

Never claim to have submitted applications, made purchases, or performed actions you did not perform.`
              },
              {
                role: "user",
                content: `Service: ${service}\nRequested language: ${language}\nUser details: ${details}\n\nPlease provide a complete, well-structured answer.`
              }
            ],
            max_tokens: 1800,
            temperature: 0.4
          }
        );

        const answer = result?.response;

        if (!answer) {
          return Response.json({
            error: "AI سے جواب موصول نہیں ہوا۔ براہِ کرم دوبارہ کوشش کریں۔"
          }, { status: 502, headers });
        }

        return Response.json({ text: answer }, { headers });
      } catch (error) {
        return Response.json({
          error: "AI جواب تیار نہیں کر سکا۔ دوبارہ کوشش کریں۔"
        }, { status: 500, headers });
      }
    }

    return env.ASSETS.fetch(request);
  }
};
