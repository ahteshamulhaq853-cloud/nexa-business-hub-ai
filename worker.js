
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/health") {
      return Response.json({
        status: "ok",
        aiConfigured: Boolean(env.AI)
      });
    }

    if (url.pathname === "/api/generate" && request.method === "POST") {
      try {
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

        if (!env.AI) {
          return Response.json(
            { error: "Workers AI binding is missing." },
            { status: 503 }
          );
        }

        const result = await env.AI.run(
          "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
          {
            messages: [
              {
                role: "system",
                content: "You are Nexa Business Hub AI, a helpful business assistant. Give clear, practical answers in the requested language. Never claim you submitted applications or performed actions you did not perform."
              },
              {
                role: "user",
                content: `Service: ${service}\nLanguage: ${language}\nDetails: ${details}`
              }
            ]
          }
        );

        return Response.json({
          text: result.response || "Please try again."
        });
      } catch (error) {
        return Response.json(
          { error: "AI request failed. Please try again." },
          { status: 500 }
        );
      }
    }

    return env.ASSETS.fetch(request);
  }
};
