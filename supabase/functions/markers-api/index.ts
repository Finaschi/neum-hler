// Neumühler See — markers API
//
// A thin, PIN-gated CRUD layer in front of the `markers` table. The table's
// RLS has no policies (see ../schema.sql), so this function — using the
// service-role key, which bypasses RLS — is the only way to reach it.
//
// Every request must carry:
//   Authorization: Bearer <anon key>   (Supabase's own default JWT check)
//   x-pin: <the shared PIN>            (our app-level gate)
//
// Routes:
//   GET    /markers-api?lake_id=<id>  -> { markers: [...] }  (markers for that lake only)
//   POST   /markers-api               -> body { type, subtype, x, z, idx, lake_id, description } -> { marker }
//   POST   /markers-api/<id>/photo    -> body { photo: <base64, no data: prefix> } -> { photo_url }
//                                         uploads to the "marker-photos" Storage bucket (must be
//                                         created + set Public in the dashboard, see BACKEND_SETUP.md)
//   PATCH  /markers-api/<id>          -> body { description?, photo_url? } -> { marker }
//                                         edits an existing marker after the fact; photo_url: null
//                                         clears the photo (use the /photo route to set a new one)
//   DELETE /markers-api/<id>          -> { ok: true }

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const PIN = Deno.env.get("MARKERS_PIN");
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-pin",
  "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

const VALID_TYPES = ["poi", "catch", "territory"];
const VALID_SUBTYPES = ["pike", "perch", "both"];

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  if (!PIN) return json({ error: "MARKERS_PIN ist auf dem Server nicht gesetzt" }, 500);
  if ((req.headers.get("x-pin") ?? "") !== PIN) {
    return json({ error: "Falsche PIN" }, 401);
  }

  const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);
  const url = new URL(req.url);
  const parts = url.pathname.split("/").filter(Boolean);
  // parts is like ["markers-api"], ["markers-api", "<id>"], or
  // ["markers-api", "<id>", "photo"]
  const isPhotoRoute = parts.length >= 2 && parts[parts.length - 1] === "photo";
  const id = isPhotoRoute
    ? parts[parts.length - 2]
    : (parts.length > 1 ? parts[parts.length - 1] : null);

  if (req.method === "POST" && isPhotoRoute) {
    if (!id) return json({ error: "Marker-ID fehlt" }, 400);
    const body = await req.json().catch(() => null);
    if (!body || typeof body.photo !== "string" || !body.photo) {
      return json({ error: "Kein Foto übergeben" }, 400);
    }
    let bytes: Uint8Array;
    try {
      const binStr = atob(body.photo);
      bytes = new Uint8Array(binStr.length);
      for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i);
    } catch {
      return json({ error: "Ungültiges Foto-Format" }, 400);
    }
    if (bytes.length > 5 * 1024 * 1024) {
      return json({ error: "Foto zu groß (max. 5 MB)" }, 400);
    }
    const path = `${id}-${Date.now()}.jpg`;
    const { error: upErr } = await supabase.storage
      .from("marker-photos")
      .upload(path, bytes, { contentType: "image/jpeg", upsert: true });
    if (upErr) return json({ error: upErr.message }, 500);
    const { data: pub } = supabase.storage.from("marker-photos").getPublicUrl(path);
    const { error: updErr } = await supabase
      .from("markers")
      .update({ photo_url: pub.publicUrl })
      .eq("id", id);
    if (updErr) return json({ error: updErr.message }, 500);
    return json({ photo_url: pub.publicUrl });
  }

  if (req.method === "GET") {
    const lakeId = url.searchParams.get("lake_id");
    let query = supabase.from("markers").select("*").order("created_at", { ascending: true });
    if (lakeId) query = query.eq("lake_id", lakeId);
    const { data, error } = await query;
    if (error) return json({ error: error.message }, 500);
    return json({ markers: data });
  }

  if (req.method === "POST") {
    const body = await req.json().catch(() => null);
    if (
      !body ||
      !VALID_TYPES.includes(body.type) ||
      (body.subtype != null && !VALID_SUBTYPES.includes(body.subtype)) ||
      typeof body.x !== "number" ||
      typeof body.z !== "number" ||
      typeof body.idx !== "number" ||
      (body.lake_id != null && typeof body.lake_id !== "string") ||
      (body.description != null && (typeof body.description !== "string" || body.description.length > 280))
    ) {
      return json({ error: "Ungültiger Marker" }, 400);
    }
    const { data, error } = await supabase
      .from("markers")
      .insert({
        type: body.type,
        subtype: body.subtype ?? null,
        x: body.x,
        z: body.z,
        idx: body.idx,
        lake_id: body.lake_id ?? "neumuehler",
        description: body.description || null,
      })
      .select()
      .single();
    if (error) return json({ error: error.message }, 500);
    return json({ marker: data }, 201);
  }

  if (req.method === "PATCH" && !isPhotoRoute) {
    if (!id || id === "markers-api") return json({ error: "Marker-ID fehlt" }, 400);
    const body = await req.json().catch(() => null);
    if (!body || typeof body !== "object") return json({ error: "Ungültige Anfrage" }, 400);
    const update: Record<string, unknown> = {};
    if ("description" in body) {
      if (body.description != null && (typeof body.description !== "string" || body.description.length > 280)) {
        return json({ error: "Ungültige Notiz" }, 400);
      }
      update.description = body.description || null;
    }
    if ("photo_url" in body) {
      if (body.photo_url != null && typeof body.photo_url !== "string") {
        return json({ error: "Ungültiges Foto" }, 400);
      }
      update.photo_url = body.photo_url || null;
    }
    if (Object.keys(update).length === 0) return json({ error: "Nichts zu aktualisieren" }, 400);
    const { data, error } = await supabase.from("markers").update(update).eq("id", id).select().single();
    if (error) return json({ error: error.message }, 500);
    return json({ marker: data });
  }

  if (req.method === "DELETE") {
    if (!id || id === "markers-api") return json({ error: "Marker-ID fehlt" }, 400);
    const { error } = await supabase.from("markers").delete().eq("id", id);
    if (error) return json({ error: error.message }, 500);
    return json({ ok: true });
  }

  return json({ error: "Methode nicht erlaubt" }, 405);
});
