
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type"
    };

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsHeaders
      });
    }

    if (url.pathname === "/api/health") {
      return Response.json(
        {
          status: "ok",
          aiConfigured: Boolean(env.AI)
        },
        { headers: corsHeaders }
      );
    }

    if (url.pathname === "/api/voice" && request.method === "POST") {
      try {
        if (!env.AI) return Response.json({error:"Cloudflare AI binding is not configured."},{status:503,headers:corsHeaders});
        const body = await request.json();
        const prompt = String(body.text || "").trim();
        if (!prompt) return Response.json({error:"Please enter text."},{status:400,headers:corsHeaders});
        if (prompt.length > 1200) return Response.json({error:"Keep text under 1,200 characters."},{status:413,headers:corsHeaders});
        const result = await env.AI.run("@cf/myshell-ai/melotts", { prompt, lang:"en" });
        const encoded = typeof result === "string" ? result : result?.audio;
        if (typeof encoded !== "string" || !encoded.length) return Response.json({error:"No audio returned. Urdu may not be supported by this model."},{status:502,headers:corsHeaders});
        const raw = atob(encoded);
        const bytes = new Uint8Array(raw.length);
        for (let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i);
        return new Response(bytes,{status:200,headers:{...corsHeaders,"Content-Type":"audio/mpeg","Content-Disposition":'inline; filename="nexa-cloudflare-voice.mp3"',"Cache-Control":"no-store"}});
      } catch (error) {
        const message = String(error?.message || "");
        const limited = /daily free allocation|neurons|quota|rate limit|limit exceeded/i.test(message);
        return Response.json({error:limited ? "Cloudflare ki daily free AI limit khatam hai. Baad mein dobara try karein." : "AI voice generate nahi hui. MeloTTS Urdu ko officially support nahi karta; result acha na ho sakta hai."},{status:limited?429:502,headers:corsHeaders});
      }
    }

    if (url.pathname === "/api/generate" && request.method === "POST") {
      try {
        const body = await request.json();

        const service = String(body.service || "")
          .trim()
          .slice(0, 150);

        const details = String(body.details || "")
          .trim()
          .slice(0, 6000);

        const language = String(body.language || "Urdu")
          .trim()
          .slice(0, 30);

        if (!service || !details) {
          return Response.json(
            { error: "براہِ کرم سروس اور تفصیلات درج کریں۔" },
            { status: 400, headers: corsHeaders }
          );
        }

        if (!env.AI) {
          return Response.json(
            { error: "Cloudflare AI binding موجود نہیں۔" },
            { status: 503, headers: corsHeaders }
          );
        }

        const result = await env.AI.run(
          "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
          {
            messages: [
              {
                role: "system",
                content: `You are Nexa Business Hub AI, a professional and helpful business assistant.

LANGUAGE:
- Respond in the language requested by the user.
- For Urdu, use natural, correct Urdu script.
- Avoid mixing Urdu with unrelated Hindi, Punjabi, or other scripts.
- Use clear headings, lists, tables when useful, and readable paragraphs.

ANSWER QUALITY:
- Give complete, practical, well-organized answers.
- Explain unfamiliar concepts in simple language.
- For business plans, include an overview, services, target customers, startup costs, monthly expenses, revenue estimates, profit calculations, marketing, risks, and practical next steps when relevant.
- Clearly label estimates and assumptions.
- Do not claim to perform actions that you have not actually performed.
- Never invent exact local prices or guarantee business success.

MATH AND FINANCIAL ACCURACY:
- Calculate all totals and subtractions carefully.
- Check arithmetic before giving the final answer.
- Distinguish revenue from expenses and net profit.
- Do not confuse startup costs with recurring monthly expenses.
- When amounts are given as ranges, calculate the minimum possible result using the minimum income and maximum expenses.
- Calculate the maximum possible result using the maximum income and minimum expenses.
- Clearly explain that these are mathematical bounds, not guaranteed outcomes.
- If monthly income is 80,000 to 170,000 PKR and monthly expenses are 42,000 to 95,000 PKR, the lowest possible difference is 80,000 - 95,000 = -15,000 PKR, and the highest possible difference is 170,000 - 42,000 = 128,000 PKR.
- Do not present a profit figure unless it follows from the numbers provided.
- Mention important excluded costs when relevant.

COMPLETENESS:
- Use enough detail to answer the request.
- Finish with a clear conclusion.
- Do not intentionally end in the middle of a sentence.
- If the answer must be concise, preserve the most important information first.

SAFETY AND HONESTY:
- Protect personal information.
- Do not request passwords or secret API keys.
- Explain uncertainties instead of making unsupported claims.`
              },
              {
                role: "user",
                content:
                  `Service: ${service}\n` +
                  `Requested language: ${language}\n` +
                  `User details: ${details}\n\n` +
                  `Provide a complete, accurate and well-structured answer. ` +
                  `Verify any calculations before presenting them.`
              }
            ],
            max_tokens: 1800,
            temperature: 0.2
          }
        );

        const answer = result?.response;

        if (typeof answer !== "string" || !answer.trim()) {
          return Response.json(
            { error: "AI سے جواب موصول نہیں ہوا۔ دوبارہ کوشش کریں۔" },
            { status: 502, headers: corsHeaders }
          );
        }

        return Response.json(
          { text: answer.trim() },
          { headers: corsHeaders }
        );
      } catch (error) {
        return Response.json(
          { error: "AI جواب تیار نہیں کر سکا۔ براہِ کرم دوبارہ کوشش کریں۔" },
          { status: 500, headers: corsHeaders }
        );
      }
    }

    return env.ASSETS.fetch(request);
  }
};
