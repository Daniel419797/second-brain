import { StitchToolClient } from "@google/stitch-sdk";

const dispatcherTimeoutMs = Math.max(10000, Number(process.env.FRIDAY_STITCH_REQUEST_TIMEOUT_MS || "480000"));
try {
  const undici = await import("undici");
  if (undici?.Agent && undici?.setGlobalDispatcher) {
    undici.setGlobalDispatcher(new undici.Agent({
      headersTimeout: dispatcherTimeoutMs,
      bodyTimeout: dispatcherTimeoutMs,
      connectTimeout: Math.min(dispatcherTimeoutMs, 60000)
    }));
  }
} catch {
  // The SDK may use the runtime fetch dispatcher directly. If undici is not
  // importable, continue with the SDK-level timeout below.
}

function pickProjectId(result) {
  const candidates = [
    result?.projectId,
    result?.id,
    result?.project?.projectId,
    result?.project?.id,
    result?.name,
  ].filter(Boolean);
  const first = String(candidates[0] || "");
  return first.includes("/") ? first.split("/").pop() : first;
}

function screenIdFrom(screen) {
  const raw = screen?.screenId || screen?.id || screen?.name || "";
  const value = String(raw || "");
  if (value.includes("/screens/")) {
    return value.split("/screens/").pop();
  }
  return value;
}

function fileUrl(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.downloadUrl || value.url || value.uri || value.href || "";
}

function looksLikeScreen(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return Boolean(
    value.htmlCode ||
    value.screenshot ||
    value.htmlUrl ||
    value.imageUrl ||
    value.screenshotUrl ||
    (typeof value.name === "string" && value.name.includes("/screens/")) ||
    (screenIdFrom(value) && (value.width || value.height || value.title))
  );
}

function sanitize(value, depth = 0) {
  if (depth > 12) return "[redacted:depth-limit]";
  if (Array.isArray(value)) {
    return value.slice(0, 200).map((item) => sanitize(item, depth + 1));
  }
  if (value && typeof value === "object") {
    const output = {};
    for (const [key, child] of Object.entries(value)) {
      if (/api.?key|token|secret|authorization|cookie|credential|password/i.test(key)) {
        output[key] = "[redacted]";
      } else {
        output[key] = sanitize(child, depth + 1);
      }
    }
    return output;
  }
  if (typeof value === "string") {
    let text = value;
    if (/^https?:\/\//i.test(text)) {
      text = text.replace(/[?#].*$/, "?[redacted]");
    }
    if (text.length > 12000) {
      text = `${text.slice(0, 12000)}...[truncated ${text.length - 12000} chars]`;
    }
    return text;
  }
  return value;
}

function collectScreens(value, path = "$", seen = new Set(), paths = [], screens = []) {
  if (!value || typeof value !== "object" || seen.has(value)) {
    return { screens, paths };
  }
  seen.add(value);
  if (looksLikeScreen(value)) {
    paths.push(path);
    screens.push({ screen: value, path });
  }
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      collectScreens(value[index], `${path}[${index}]`, seen, paths, screens);
    }
    return { screens, paths };
  }
  for (const [key, child] of Object.entries(value)) {
    collectScreens(child, `${path}.${key}`, seen, paths, screens);
  }
  return { screens, paths };
}

function explicitProjectionScreens(raw) {
  const attempts = [];
  const screens = [];
  function pushFrom(candidate, path) {
    attempts.push(path);
    if (Array.isArray(candidate)) {
      candidate.forEach((screen, index) => {
        if (looksLikeScreen(screen)) screens.push({ screen, path: `${path}[${index}]` });
      });
    } else if (looksLikeScreen(candidate)) {
      screens.push({ screen: candidate, path });
    }
  }
  const outputComponents = raw?.outputComponents || raw?.output_components || [];
  if (Array.isArray(outputComponents)) {
    outputComponents.forEach((component, index) => {
      pushFrom(component?.design?.screens, `outputComponents[${index}].design.screens`);
      pushFrom(component?.design?.screen, `outputComponents[${index}].design.screen`);
      pushFrom(component?.screens, `outputComponents[${index}].screens`);
      pushFrom(component?.screen, `outputComponents[${index}].screen`);
      pushFrom(component?.payload?.design?.screens, `outputComponents[${index}].payload.design.screens`);
      pushFrom(component?.data?.design?.screens, `outputComponents[${index}].data.design.screens`);
    });
  } else {
    attempts.push("outputComponents");
  }
  pushFrom(raw?.design?.screens, "design.screens");
  pushFrom(raw?.screens, "screens");
  pushFrom(raw?.screen, "screen");
  pushFrom(raw?.generatedScreen, "generatedScreen");
  pushFrom(raw?.generated_screen, "generated_screen");
  return { screens, attempts };
}

function extractScreens(raw) {
  const explicit = explicitProjectionScreens(raw);
  const deep = collectScreens(raw);
  const seen = new Set();
  const screens = [];
  for (const item of [...explicit.screens, ...deep.screens]) {
    const id = screenIdFrom(item.screen);
    const marker = `${id || ""}|${item.path}`;
    if (seen.has(marker)) continue;
    seen.add(marker);
    screens.push(item);
  }
  return {
    screens,
    paths: [...new Set([...explicit.attempts, ...deep.paths])]
  };
}

function outputTextFrom(raw) {
  const components = raw?.outputComponents || raw?.output_components || [];
  const texts = [];
  if (Array.isArray(components)) {
    for (const component of components) {
      for (const key of ["text", "message", "content", "suggestion", "suggestions"]) {
        const value = component?.[key];
        if (typeof value === "string") texts.push(value);
        if (Array.isArray(value)) texts.push(...value.filter((item) => typeof item === "string"));
      }
    }
  }
  return texts.join("\n").slice(0, 2000);
}

function screenQuality(screen) {
  const mime = String(screen?.htmlCode?.mimeType || screen?.html?.mimeType || "").toLowerCase();
  const titleText = `${screen?.title || ""} ${screen?.prompt || ""}`.toLowerCase();
  const width = Number(screen?.width || 0);
  const height = Number(screen?.height || 0);
  let score = 0;
  if (mime.includes("text/html")) score += 50;
  if (mime.includes("image/svg")) score -= 45;
  if (width >= 1000) score += 10;
  if (height >= 900) score += 15;
  if (height >= 1800) score += 10;
  if (/\b(home|atelier|collections?|concierge|contact|about|services?|page|website|landing)\b/.test(titleText)) score += 10;
  if (/\b(logo|icon|mark|symbol|brand asset)\b/.test(titleText)) score -= 35;
  if (screen?.screenshot || screen?.screenshotUrl || screen?.imageUrl) score += 5;
  return score;
}

function rankedScreens(items) {
  return [...items]
    .map((item, index) => ({ ...item, originalIndex: index, quality: screenQuality(item.screen) }))
    .sort((left, right) => (right.quality - left.quality) || (left.originalIndex - right.originalIndex));
}

function toPayload(screen, label, sourcePath) {
  const screenId = screenIdFrom(screen);
  return {
    id: screenId || screen?.id || label,
    label,
    projectId,
    screenId,
    title: screen?.title || "",
    htmlUrl: screen?.htmlUrl || screen?.htmlCodeUrl || fileUrl(screen?.htmlCode) || fileUrl(screen?.html),
    imageUrl: screen?.imageUrl || screen?.screenshotUrl || fileUrl(screen?.screenshot) || fileUrl(screen?.image),
    sourcePath
  };
}

function parseJsonEnv(value, fallback) {
  try {
    const parsed = JSON.parse(value || "");
    return parsed && typeof parsed === "object" ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function compactJson(value, maxLength = 1200) {
  let text = "";
  try {
    text = JSON.stringify(value || {});
  } catch {
    text = String(value || "");
  }
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

function asList(value, limit = 8) {
  return Array.isArray(value) ? value.filter(Boolean).slice(0, limit) : [];
}

function joinList(value, limit = 8) {
  return asList(value, limit).map((item) => String(item)).join(", ");
}

function contextLine(label, value) {
  const text = Array.isArray(value) ? joinList(value, 10) : String(value || "").trim();
  return text ? `- ${label}: ${text}` : "";
}

function compilePromptFromContext(ctx, fallbackPrompt = "") {
  const userIntent = ctx?.user_intent || {};
  const creative = ctx?.creative_brief || {};
  const composition = ctx?.composition_spec || {};
  const experience = ctx?.experience_mode || {};
  const content = ctx?.content_model || {};
  const copy = ctx?.copy_bank || {};
  const output = ctx?.output_contract || {};
  const brand = ctx?.brand_system || {};
  const site = ctx?.site_continuity || {};
  const taxonomy = ctx?.taxonomy_prompt_profile || {};
  const visualMemory = ctx?.visual_reference_memory || {};
  const lines = [
    "Design context package:",
    contextLine("User intent", userIntent.raw_request),
    contextLine("Product goal", ctx?.product_goal),
    contextLine("Target audience", ctx?.target_audience),
    contextLine("Emotional intent", ctx?.emotional_intent),
    contextLine("Core message", ctx?.message),
    "",
    "First viewport composition:",
    contextLine("Composition archetype", composition.archetype_name || composition.archetype),
    contextLine("Archetype rationale", composition.archetype_rationale),
    ...asList(composition.allowed_archetypes, 4).map((item) => {
      if (!item || typeof item !== "object") return `- Alternative archetype: ${String(item)}`;
      return `- Alternative archetype: ${item.name || item.id}: ${item.first_viewport || item.why || ""}`;
    }),
    ...asList(composition.composition_rules, 5).map((item) => `- Composition rule: ${item}`),
    ...asList(composition.first_viewport, 5).map((item) => `- ${item}`),
    contextLine("Visual hierarchy", composition.visual_hierarchy),
    contextLine("Variant policy", composition.variant_policy),
    "",
    "Experience mode and motion/3D contract:",
    contextLine("Experience mode", experience.mode_name || experience.mode),
    contextLine("Intent", experience.intent),
    contextLine("Recommended libraries", experience.recommended_libraries),
    ...asList(experience.allowed_modes, 4).map((item) => {
      if (!item || typeof item !== "object") return `- Alternative mode: ${String(item)}`;
      return `- Alternative mode: ${item.name || item.id}: ${item.intent || item.when_to_use || ""}`;
    }),
    ...asList(experience.implementation_notes, 6).map((item) => `- Implementation note: ${item}`),
    ...asList(experience.motion_rules, 6).map((item) => `- Motion rule: ${item}`),
    ...asList(experience.verification_requirements, 6).map((item) => `- Verify: ${item}`),
    contextLine("Fallback requirement", experience.fallback_requirement),
    contextLine("Performance budget", compactJson(experience.performance_budget || {}, 900)),
    "",
    "Required sections:",
    ...asList(ctx?.section_blueprint, 8).map((item) => {
      if (!item || typeof item !== "object") return `- ${String(item)}`;
      return `- ${item.section || "Section"}: ${item.purpose || ""} Must show: ${joinList(item.must_show, 8)}. Visual objects: ${joinList(item.visual_objects, 6)}.`;
    }),
    "",
    "Component inventory:",
    contextLine("Components", ctx?.component_inventory),
    "",
    "Copy bank:",
    contextLine("Headline directions", copy.headline_directions),
    contextLine("Subhead direction", copy.subhead_direction),
    contextLine("Microcopy examples", copy.microcopy_examples),
    contextLine("Words to avoid", copy.words_to_avoid),
    "",
    "Visual grammar:",
    contextLine("Direction", ctx?.visual_context?.direction),
    contextLine("Palette", ctx?.visual_context?.palette),
    contextLine("Typography", ctx?.visual_context?.typography),
    contextLine("Imagery", ctx?.visual_context?.imagery),
    contextLine("Brand tokens", compactJson(brand.tokens || {}, 900)),
    contextLine("Logo direction", brand.logo_direction),
    contextLine("Site continuity", compactJson(site.site_design_system || {}, 1200)),
    contextLine("Approved visual references", compactJson(visualMemory.assets || [], 900)),
    "",
    "Taxonomy-specific guidance:",
    contextLine("Message", taxonomy.message),
    contextLine("Emotional feel", taxonomy.emotional_feel),
    contextLine("Rejection rules", taxonomy.rejection_rules),
    "",
    "Rejection rules:",
    ...asList(output.rejection_if, 8).map((item) => `- ${item}`),
    "- Do not generate placeholder numbered labels like Home 1, Home 2, Service 1, or Service 2.",
    "- Do not render internal style profile names unless the requested product brand is that exact name.",
    "- Normalize exaggerated scale so the first viewport is usable and copy is not clipped.",
    "",
    "Variant instructions:",
    ...asList(ctx?.variant_briefs, 3).map((item) => `- ${item.variant || "Variant"}: ${item.direction || ""} ${item.must_change || ""}`),
    "",
    "Output contract:",
    ...asList(output.must_return, 6).map((item) => `- Must return: ${item}`),
    contextLine("Minimum depth", output.minimum_depth),
    "",
    "Code/product signals:",
    compactJson(ctx?.code_context || {}, 1000),
    "Design-system context:",
    compactJson(ctx?.design_system_context || {}, 1000),
  ].filter((line) => line !== "");
  const compiled = lines.join("\n");
  return compiled.length >= 1200 ? compiled : fallbackPrompt;
}

function fitPromptBudget(text, ctx, budget) {
  const maxLength = Math.max(6000, Number(budget || 12000));
  const candidate = String(text || "").trim() || compilePromptFromContext(ctx, "");
  if (candidate.length <= maxLength) return candidate;
  const fromContext = compilePromptFromContext(ctx, candidate);
  if (fromContext && fromContext.length <= maxLength) return fromContext;
  const outputContract = [
    "\n\nOutput contract:",
    "- Return a complete desktop screen/page, not a logo or isolated component.",
    "- Include specific visible copy, semantic sections, usable controls, and responsive structure.",
    "- Reject placeholder numbered labels, generic scaffold copy, oversized clipped hero type, and off-domain visuals."
  ].join("\n");
  const room = Math.max(1000, maxLength - outputContract.length - 80);
  return `${fromContext.slice(0, room)}\n\n[Prompt compacted by Friday StitchPromptCompiler to preserve critical context.]${outputContract}`;
}

const prompt = process.env.FRIDAY_STITCH_PROMPT || "";
const contextJson = parseJsonEnv(process.env.FRIDAY_STITCH_CONTEXT_JSON || "{}", {});
const compiledEnvPrompt = process.env.FRIDAY_STITCH_COMPILED_PROMPT || "";
const promptBudgetChars = Math.max(6000, Number(process.env.FRIDAY_STITCH_PROMPT_BUDGET_CHARS || "12000"));
const title = process.env.FRIDAY_STITCH_TITLE || "Friday Design";
const variantCount = Math.max(1, Math.min(3, Number(process.env.FRIDAY_STITCH_VARIANT_COUNT || "1")));
let variantDirections = [];
try {
  const parsedDirections = JSON.parse(process.env.FRIDAY_STITCH_VARIANT_DIRECTIONS || "[]");
  variantDirections = Array.isArray(parsedDirections) ? parsedDirections.filter((item) => typeof item === "string" && item.trim()) : [];
} catch {
  variantDirections = [];
}
const modelId = process.env.FRIDAY_STITCH_MODEL_ID || "GEMINI_3_1_PRO";
const requestTimeoutMs = Math.max(10000, Number(process.env.FRIDAY_STITCH_REQUEST_TIMEOUT_MS || "240000"));
const variantTimeoutMs = Math.max(5000, Number(process.env.FRIDAY_STITCH_VARIANT_TIMEOUT_MS || "60000"));
const fallbackVariantsEnabled = process.env.FRIDAY_STITCH_FALLBACK_VARIANTS === "1";
let projectId = process.env.FRIDAY_STITCH_PROJECT_ID || "";
const startedAt = Date.now();
function log(stage, extra = "") {
  console.error(`[friday-stitch] ${stage}${extra ? ` ${extra}` : ""} ${Date.now() - startedAt}ms`);
}
const toolClient = new StitchToolClient({ apiKey: process.env.STITCH_API_KEY, timeout: requestTimeoutMs });
const warnings = [];
const rawGetScreens = [];
const rawFallbackGenerations = [];
let rawGenerate = null;
let rawVariants = null;
const compactPrompt = fitPromptBudget(compiledEnvPrompt || prompt || compilePromptFromContext(contextJson, prompt), contextJson, promptBudgetChars);
function directionFor(index) {
  return variantDirections[(Math.max(1, index) - 1) % Math.max(1, variantDirections.length)] || "change the composition, hierarchy, content emphasis, visual rhythm, and interaction model while keeping the same product and domain.";
}
const attempts = Math.max(1, Math.min(3, Number(process.env.FRIDAY_STITCH_GENERATE_ATTEMPTS || "2")));
function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
function withTimeout(promise, ms, message) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}
async function generateWithRetry(generatePrompt, label) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      log(`generate_screen_from_text:${label}:start`, `attempt=${attempt} model=${modelId}`);
      const raw = await toolClient.callTool("generate_screen_from_text", {
        projectId,
        prompt: generatePrompt,
        deviceType: "DESKTOP",
        modelId
      });
      log(`generate_screen_from_text:${label}:done`, `session=${raw?.sessionId || raw?.session_id || ""}`);
      return raw;
    } catch (error) {
      lastError = error;
      warnings.push(`${label} attempt ${attempt} failed: ${error?.message || String(error)}`);
      log(`generate_screen_from_text:${label}:error`, error?.message || String(error));
      if (attempt < attempts) {
        await wait(1500 * attempt);
      }
    }
  }
  throw lastError;
}
async function enrichPayload(payload, label) {
  if (!payload.screenId || (payload.htmlUrl && payload.imageUrl)) {
    return payload;
  }
  try {
    log(`get_screen:${label}:start`, payload.screenId);
    const raw = await toolClient.callTool("get_screen", {
      projectId,
      screenId: payload.screenId,
      name: `projects/${projectId}/screens/${payload.screenId}`
    });
    rawGetScreens.push({ screenId: payload.screenId, response: sanitize(raw) });
    const detail = toPayload({ ...raw, projectId }, label, "get_screen");
    log(`get_screen:${label}:done`);
    return {
      ...payload,
      htmlUrl: payload.htmlUrl || detail.htmlUrl,
      imageUrl: payload.imageUrl || detail.imageUrl,
      title: payload.title || detail.title
    };
  } catch (error) {
    warnings.push(`get_screen failed for ${payload.screenId}: ${error?.message || String(error)}`);
    log(`get_screen:${label}:error`, error?.message || String(error));
    return payload;
  }
}
async function main() {
  if (!projectId) {
    log("create_project:start");
    const project = await toolClient.callTool("create_project", { title });
    projectId = pickProjectId(project);
    log("create_project:done", projectId);
  } else {
    log("project:reuse", projectId);
  }
  if (!projectId) {
    throw new Error("Stitch did not return a project id.");
  }
  rawGenerate = await generateWithRetry(compactPrompt, "base");
  const baseExtraction = extractScreens(rawGenerate);
  const rankedBaseScreens = rankedScreens(baseExtraction.screens);
  if (!rankedBaseScreens.length) {
    const error = "Stitch generate_screen_from_text returned no screen in known projection paths.";
    console.log(JSON.stringify({
      ok: false,
      status: "no_screen",
      provider: "stitch",
      projectId,
      modelId,
      error,
      outputText: outputTextFrom(rawGenerate),
      projectionPathsTried: baseExtraction.paths,
      rawGenerate: sanitize(rawGenerate),
      warnings
    }));
    process.exitCode = 2;
    return;
  }
  const variants = [];
  const seenVariantKeys = new Set();
  const baseLimit = variantCount <= 1 ? Math.min(rankedBaseScreens.length, 1) : Math.min(rankedBaseScreens.length, Math.max(variantCount, 6));
  for (let index = 0; index < baseLimit; index += 1) {
    const item = rankedBaseScreens[index];
    const label = index === 0 ? "Base direction" : `Base screen ${index + 1}`;
    const payload = await enrichPayload(toPayload(item.screen, label, item.path), `base ${index + 1}`);
    const marker = `${payload.screenId || payload.id || ""}|${payload.htmlUrl || ""}|${payload.imageUrl || ""}`;
    if (!seenVariantKeys.has(marker)) {
      seenVariantKeys.add(marker);
      variants.push(payload);
    }
  }
  console.log(JSON.stringify({
    ok: true,
    status: "base_generated",
    provider: "stitch",
    projectId,
    modelId,
    screenId: variants[0]?.screenId || "",
    htmlUrl: variants[0]?.htmlUrl || "",
    imageUrl: variants[0]?.imageUrl || "",
    variants,
    projectionPathsTried: baseExtraction.paths,
    rawGenerate: sanitize(rawGenerate),
    rawVariants: null,
    rawGetScreens,
    rawFallbackGenerations,
    warnings: [...warnings, "Base Stitch generation checkpoint captured before optional variant exploration."]
  }));
  if (variantCount > 1 && variants[0]?.screenId && variants.length < variantCount) {
    try {
      log("generate_variants:start", `count=${variantCount - 1} model=${modelId}`);
      rawVariants = await withTimeout(
        toolClient.callTool("generate_variants", {
          projectId,
          selectedScreenIds: [variants[0].screenId],
          prompt: `Create genuinely distinct alternatives for the same product. Preserve domain-specific copy, improve hierarchy, accessibility, and operational workflow clarity. Use these art directions: ${variantDirections.join(" / ") || "change layout, visual language, and interaction model"}. Do not use internal style profile names as visible branding.`,
          variantOptions: {
            variantCount: variantCount - 1,
            creativeRange: "EXPLORE",
            aspects: ["LAYOUT", "COLOR_SCHEME", "TEXT_CONTENT"]
          },
          deviceType: "DESKTOP",
          modelId
        }),
        variantTimeoutMs,
        `generate_variants timed out after ${variantTimeoutMs}ms`
      );
      const extractedVariants = extractScreens(rawVariants);
      log("generate_variants:done", String(extractedVariants.screens.length));
      for (let index = 0; index < extractedVariants.screens.length; index += 1) {
        const item = extractedVariants.screens[index];
        variants.push(await enrichPayload(toPayload(item.screen, `Exploration ${index + 1}`, item.path), `variant ${index + 1}`));
      }
      if (!extractedVariants.screens.length) {
        warnings.push("variant API returned no screens in known projection paths.");
      }
    } catch (error) {
      warnings.push(`variant API failed: ${error?.message || String(error)}. Continuing with the base Stitch screen.`);
      log("generate_variants:error", error?.message || String(error));
      if (fallbackVariantsEnabled) {
        warnings.push("fallback variant generation is enabled; attempting separate generated screens.");
        for (let index = 1; index < variantCount; index += 1) {
          const rawFallback = await generateWithRetry(`${compactPrompt}\n\nAlternative design ${index}: ${directionFor(index)} Do not repeat the base composition.`, `fallback ${index}`);
          rawFallbackGenerations.push(sanitize(rawFallback));
          const extractedFallback = extractScreens(rawFallback);
          if (extractedFallback.screens[0]) {
            const payload = await enrichPayload(toPayload(extractedFallback.screens[0].screen, `Generated alternative ${index}`, extractedFallback.screens[0].path), `fallback ${index}`);
            const marker = `${payload.screenId || payload.id || ""}|${payload.htmlUrl || ""}|${payload.imageUrl || ""}`;
            if (!seenVariantKeys.has(marker)) {
              seenVariantKeys.add(marker);
              variants.push(payload);
            }
          } else {
            warnings.push(`fallback ${index} returned no screen in known projection paths.`);
          }
        }
      } else {
        warnings.push("fallback variant generation is disabled; base Stitch screen remains eligible for critique.");
      }
    }
  }
  const htmlUrl = variants[0]?.htmlUrl || "";
  const imageUrl = variants[0]?.imageUrl || "";
  console.log(JSON.stringify({
    ok: true,
    provider: "stitch",
    projectId,
    modelId,
    screenId: variants[0]?.screenId || "",
    htmlUrl,
    imageUrl,
    variants,
    projectionPathsTried: baseExtraction.paths,
    rawGenerate: sanitize(rawGenerate),
    rawVariants: rawVariants ? sanitize(rawVariants) : null,
    rawGetScreens,
    rawFallbackGenerations,
    warnings
  }));
}
try {
  await main();
} catch (error) {
  console.log(JSON.stringify({
    ok: false,
    status: "failed",
    provider: "stitch",
    projectId,
    modelId,
    error: error?.message || String(error),
    rawGenerate: rawGenerate ? sanitize(rawGenerate) : null,
    rawVariants: rawVariants ? sanitize(rawVariants) : null,
    rawGetScreens,
    rawFallbackGenerations,
    warnings
  }));
  process.exitCode = process.exitCode || 1;
} finally {
  log("close:start");
  await toolClient.close?.();
  log("close:done");
}
