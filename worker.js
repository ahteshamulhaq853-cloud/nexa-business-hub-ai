
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/health") {
      return Response.json({
        status: "ok",
        aiConfigured: Boolean(env.OPENAI_API_KEY)
      });
    }

    if (url.pathname === "/api/generate" && request.method === "POST") {
      try {
        if (!env.OPENAI_API_KEY) {
          return Response.json(
            { error: "AI API key is not configured." },
            { status: 503 }
          );
        }

        const body = await request.json();
        const service = String(body.service || "").slice(0, 150);
        const details = String(body.details || "").slice(0, 6000);
        const language = String(body.language || "Urdu").slice(0, 30);

        if (!service || !details) {
          return Response.json(
            { error: "Please enter the service and details." },
            { status: 400 }
          );
        }

        const response = await fetch(
          "https://api.openai.com/v1/responses",
          {
            method: "POST",
            headers: {
              "Authorization": `Bearer ${env.OPENAI_API_KEY}`,
              "Content-Type": "application/json"
            },
            body: JSON.stringify({
              model: "gpt-4.1-mini",
              instructions:
                "You are Nexa Business Hub AI. Give helpful, clear and practical business assistance. Never claim to submit applications or perform actions you did not perform.",
              input: `Service: ${service}\nLanguage: ${language}\nUser details: ${details}`
            })
          }
        );

        const data = await response.json();

        if (!response.ok) {
          return Response.json(
            { error: "AI service request failed. Check API settings." },
            { status: 502 }
          );
        }

        const answer = (data.output || [])
          .flatMap(item => item.content || [])
          .filter(item => item.type === "output_text")
          .map(item => item.text)
          .join("\n");

        return Response.json({ text: answer });
      } catch {
        return Response.json(
          { error: "Request failed. Please try again." },
          { status: 500 }
        );
      }
    }

    return env.ASSETS.fetch(request);
  }
};
