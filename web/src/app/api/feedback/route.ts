import { recordProductFeedback } from "@/lib/server/feedback";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const productId = Number(body?.productId);
    if (!Number.isInteger(productId) || typeof body?.helpful !== "boolean") {
      return Response.json({ error: "Richiesta non valida." }, { status: 400 });
    }
    recordProductFeedback(productId, body.helpful);
    return Response.json({ ok: true });
  } catch (error) {
    console.error("Impossibile salvare il feedback", error);
    return Response.json({ error: "Feedback non salvato." }, { status: 500 });
  }
}
