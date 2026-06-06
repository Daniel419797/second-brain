# Design Provider Plan

Product: Vale & Vellum
Request: Build a website design for Vale & Vellum, a boutique stationery and wedding invitation studio for couples, planners, and small luxury events. Use Friday's design-only workflow. Do not implement frontend code. Do not create a Next.js app. Save the Stitch design artifacts so the user can inspect the UI directly. Project goals: - Present Vale & Vellum as an elegant but modern paper studio, not a generic SaaS or template website. - Sell custom wedding invitation suites, event stationery, menus, place cards, wax seals, and concierge design packages. - Make the first viewport feel tactile, editorial, romantic, and premium without becoming beige and boring. - The site should support four pages conceptually: Home, Collections, Process, Inquiry. Generate the main website/homepage UI with enough content depth to imply the full site direction. Design direction: - Category: luxury / fashion-adjacent / editorial commerce. - Emotional feel: quiet romance, craft, ceremony, intimacy, precision, warm confidence. - Composition archetype: full-bleed editorial hero or image-led asymmetric editorial layout. Avoid the standard left-text/right-card SaaS hero. - Visual grammar: macro paper texture, foil impression, invitation stack, handwritten proof marks, refined serif headline, crisp sans labels, generous whitespace, tactile product details, restrained accent color. - Copy voice: specific, sensory, polished, never generic. Use language about paper stock, foil, letterpress, vellum wraps, hand assembly, planner deadlines, guest count, proof rounds, and concierge delivery. Required sections for the generated UI: 1. Hero with strong product signal: invitation suite / paper stack / tactile detail. It must not be hero-only; it should lead into content. 2. Collection preview: Signature Suites, Weekend Details, Bespoke Editorial, Planner Concierge. 3. Process: consultation, material direction, proofing, production, delivery. 4. Proof/credibility: production timelines, sample kit, planner-friendly deliverables, rush option. 5. Inquiry CTA with guest count / event date / package path. Rejection rules: - Reject generic SaaS dashboard cards, vague startup copy, empty dark sections, washed/blurry images, giant text that cuts off, one-section pages, placeholder menu labels like Home 1, Service 2, or lorem ipsum. - Do not use oversized rounded cards or a split hero with a fake analytics panel. - Do not make it dominated by beige alone; use a richer palette with ivory, ink, muted rose, deep olive, and foil/bronze accents. Brand name: Vale & Vellum. Page label: conceptually: Home. Route: /conceptually-home. Design the conceptually: Home page for Vale & Vellum. This is one page in a cohesive multi-page website. Page focus: brand, offer, proof, primary call to action. Site map: conceptually: Home (/conceptually-home); Collections (/collections); Process (/process); Inquiry (/inquiry). Visible logo and brand copy must say Vale & Vellum, not Vale & Vellum conceptually: Home. Do not render conceptually: Home as a giant eyebrow, standalone H1, numbered tab, or section title just because it is the route label. Do not label sections as Page 1, Home 1, Services 2, or similar numbered filler. Design only this route's page content; other pages should appear only as navigation links or short teasers where appropriate, never as repeated full sections. Use real route links from this site map (conceptually: Home (/conceptually-home); Collections (/collections); Process (/process); Inquiry (/inquiry)) rather than # placeholders or default routes that are not in the site map. Do not return only a logo, icon, brand mark, style guide, or isolated asset; return a complete page screen with navigation, main content, and footer. Keep the same design system across pages. Generate a complete page, not only a hero. Use production web proportions: desktop H1 around 40-58px, readable sections, no oversized whitespace, no sticky header overlap, no giant display type, and no decorative excess. Use structured sections that Friday can convert into Next.js routes without duplicating the hero.

## Provider Policy
- Stitch: ready - Stitch SDK is configured for UI design generation.
- v0: blocked - Set V0_API_KEY only if you want Friday to use v0.
- Local style memory: ready - Local style profiles are file/database memory and do not require paid API calls.

## Style Memory
- Profile: NexusForge Next.js

## Design Contract
- Page: Conceptually Home
- Objective: Design the Conceptually Home route for a real multi-page website, with navigation to conceptually: Home, Collections, Process, Inquiry. The page label is route metadata, not a visible hero headline by itself.
- Required sections: global navigation, brand-specific hero, trust/proof teaser, service teaser, primary contact CTA
- Scale rule: Use restrained production UI scale: no oversized headings that exceed one viewport, no decorative empty whitespace, and no section taller than its useful content.

## Brief Autopilot
- Active: False
- Expanded request: Build a website design for Vale & Vellum, a boutique stationery and wedding invitation studio for couples, planners, and small luxury events. Use Friday's design-only workflow. Do not implement frontend code. Do not create a Next.js app. Save the Stitch design artifacts so the user can inspect the UI directly. Project goals: - Present Vale & Vellum as an elegant but modern paper studio, not a generic SaaS or template website. - Sell custom wedding invitation suites, event stationery, menus, place cards, wax seals, and concierge design packages. - Make the first viewport feel tactile, editorial, romantic, and premium without becoming beige and boring. - The site should support four pages conceptually: Home, Collections, Process, Inquiry. Generate the main website/homepage UI with enough content depth to imply the full site direction. Design direction: - Category: luxury / fashion-adjac...
- Assumption: The request includes a usable product/company signal; Friday expanded missing design details only.
- Smart default: luxury_editorial_tactile
- Selected direction: cinematic_product_led
- Research status: live_research_complete

## Art Direction
- Direction: quiet luxury with editorial restraint and tactile detail
- Visual language: large negative space, close-up materials, elegant asymmetry, slow reveal
- Layout signature: immersive hero, provenance story, product/editorial modules, appointment or concierge path
- Palette: warm ivory, ink, charcoal, metallic or jewel accent used sparingly
- Variant direction: Editorial luxury lookbook with immersive imagery, provenance, and discreet concierge action.
- Variant direction: Boutique product story with material close-ups, collection modules, and appointment path.
- Variant direction: Private-client service page with restrained typography, trust cues, and high-touch contact flow.
- Use src/app only for routes, layouts, route handlers, and route-local boundaries.
- Put real feature UI in src/components/<FeatureName>.
- Put generic primitives in src/components/ui.
- Put navigation and shell components in src/components/layout.
- Put API clients and response normalization in src/services.
- Put shared browser state in src/store.
- Put reusable client workflows in src/hooks.
- Put domain helpers, utilities, security helpers, and product contracts in src/lib.
- Put shared DTOs and UI contracts in src/types.
- Keep tests colocated in __tests__ or shared under src/test.
- Do not put large feature UI, state, services, and route logic into one blob.

## Rich Design Context
- Product goal: Help visitors understand Vale & Vellum, trust the offer, compare the value, and take the next step without generic filler or oversized brochure sections.
- Target audience: first-time visitors deciding whether to trust the product, high-intent private clients, collectors, concierge buyers, brand loyalists
- Emotional intent: desire, restraint, intimacy, confidence, exclusivity
- Core message: The brand is scarce, crafted, and worth slowing down for.
- Inspiration direction: Quiet editorial luxury: Premium brands need restraint, materiality, white space, and concierge confidence.
- Inspiration direction: Evidence-first product page: Visitors should see proof, workflow, and CTA before decorative storytelling.
- Inspiration direction: Production interface handoff: The design must convert into real components, not a static poster.
- Learned rules: 10 learned rule(s) selected for this request.
- Context artifacts: design-context.json, DESIGN.md, stitch-prompt.md, and site-design-system.json
- Stitch prompt compilation: 11174/12000 chars

## Stitch Prompt

Design context package:
- Critical rejection rule: Do not use generic SaaS dashboard imagery for a non-SaaS company website.
- Domain copy guardrail: Never let internal prompt labels, route labels, or scaffold phrases become visible product copy.
- canvas/WebGL or scene layer required for immersive/3D modes; include static and reduced-motion fallback.
- Do not default to a left-text/right-card split hero.
- Product goal: Help visitors understand Vale & Vellum, trust the offer, compare the value, and take the next step without generic filler or oversized brochure sections.
- Emotional intent: desire, restraint, intimacy, confidence, exclusivity
- Design default hero composition: full-bleed product/media hero or immersive scene with crisp product detail
- Critique before code: judge beauty, hero strength, image clarity, c
- [Section compacted by Friday StitchPromptCompiler.]

Brief Autopilot:
- Treat vague prompts as incomplete briefs, not permission for generic output.
- Autopilot active: False (vague=False, style_missing=False, product_missing=False)
- Assumption/clarification policy: The request includes a usable product/company signal; Friday expanded missing design details only.
- Hero composition to request: full-bleed product/media hero or immersive scene with crisp product detail
- Critique before code: reject weak Stitch results before frontend implementation.
- Product/company type: luxury company website
- Target users: first-time visitors deciding whether to trust the product, high-intent private clients, collectors, concierge buyers, brand loyalists
- Page goal: Help visitors understand the product/company, trust it, inspect proof, and take a clear next step.
- Business model: premium direct-to-consumer or private inquiry sales
- Smart default: luxury_editorial_tactile. Reason: Luxury should signal scarcity, cr
- [Section compacted by Friday StitchPromptCompiler.]

Research evidence before design:
- Research status: planned; live=False
- Competitor/user-need inference: Research plan prepared; live search was not run.
- Use research as evidence, not as certainty. If evidence is thin, keep assumptions visible.

Creative brief:
- One-sentence feel: Vale & Vellum should feel like quiet luxury with editorial restraint and tactile detail.
- Decision moment: A high-intent private client is deciding whether the brand feels rare, crafted, and worthy of a personal inquiry.
- Primary objection to overcome: The experience can feel mass-market, loud, or insufficiently premium.
- Design answer: Use restraint, material detail, provenance, appointment paths, and quiet confidence instead of badges or discounts.
- [Section compacted by Friday StitchPromptCompiler.]

Concrete page composition:
- Composition archetype: Full-Bleed Media Hero
- Archetype rationale: Physical, visual, luxury, fashion, construction, real estate, and story-led brands need place, material, or people to carry the first impression.
- Allowed alternative archetype: Full-Bleed Media Hero: Full-bleed image, video, rendered scene, or strong visual background with text anchored directly on the media, not inside a floating card.
- Allowed alternative archetype: Workflow Stage: Problem state, AI/action state, approval/audit state, and outcome are staged as one product workflow.
- Allowed alternative archetype: Editorial Asymmetric: Asymmetric headline, image crop, metadata, and proof arranged like a designed editorial spread.
- Allowed alternative archetype: Centered Statement Hero: Centered or left-anchored headline over a quiet background system, with CTAs and the next proof section peeking into view.
- Compo
- [Section compacted by Friday StitchPromptCompiler.]

Experience mode and motion/3D contract:
- Experience mode: Data Visualization Motion
- Intent: Use animated charts/maps/timelines to make data, trends, or operational state understandable.
- Recommended libraries: Recharts, D3 optional, Framer Motion optional
- Allowed alternate mode: Data Visualization Motion: Use animated charts/maps/timelines to make data, trends, or operational state understandable.
- Allowed alternate mode: Editorial Luxury: Create a premium, art-directed experience with restraint, asymmetry, tactile imagery, and slow confidence.
- Allowed alternate mode: Cinematic Scroll: Use scroll progression, layered sections, pinned moments, and reveal timing to tell a product or brand story.
- Allowed alternate mode: Parallax Story: Use depth, foreground/background motion, and anchored content to create visual drama without requiring full 3D.
- Implementation note: charts
- Implementation note: maps
- Im
- [Section compacted by Friday StitchPromptCompiler.]

Section-by-section blueprint:
- Hero: Create desire with brand, material detail, and a discreet action. Must show: brand statement, hero image, concierge CTA. Visual objects: editorial hero, material close-up.
- Provenance: Show why the object/service is rare and credible. Must show: craft, materials, heritage. Visual objects: story panel, detail modules.
- Collection or offer: Let the visitor inspect options without ecommerce clutter. Must show: collection, fit, scarcity. Visual objects: lookbook grid, product cards.
- Concierge path: Make the next step private and high-touch. Must show: appointment, inquiry, response promise. Visual objects: concierge form, contact strip.

Component inventory to design:
- chart/map/timeline surface
- legend and labels
- data filter controls
- editorial hero
- material image field
- provenance cards
- lookbook modules
- concierge inquiry form

Copy and content requirements:
- Navigation: conceptually: Home, Collections, Process, Inquiry
- Primary CTAs: Request concierge access, Explore collection
- Proof objects: client proof, process step, result metric, response promise
- Headline directions: Crafted for private clients who notice the difference. / A quieter standard of luxury, made visible. / Objects and experiences with provenance.
- Subhead direction: Vale & Vellum should communicate The brand is scarce, crafted, and worth slowing down for. in a spare, sensorial, confident, never loud voice.
- Microcopy examples: Request concierge access, View the collection, Private appointment
- Words to use: vale, vellum, boutique, stat
- [Section compacted by Friday StitchPromptCompiler.]

Brand system:
- Logo direction: quiet wordmark for Vale & Vellum; refined spacing, no loud badge
- Typography pair: {"body": "clean readable sans", "display": "editorial serif or high-contrast display", "mono": "not primary"}
- Color tokens: {"accent": "#9f6b3e", "accent_2": "#2f2924", "bg": "#f7f1e8", "border": "#ded2c3", "danger": "#9f1239", "muted": "#71675e", "success": "#3f6f53", "surface": "#fffaf3", "surface_2": "#14110f", "text": "#17120d", "warning": "#b7791f"}
- Spacing scale: {'x
- [Section compacted by Friday StitchPromptCompiler.]

Visual grammar:
- Art direction: quiet luxury with editorial restraint and tactile detail
- Message: The brand is scarce, crafted, and worth slowing down for.
- Emotional feel: desire, restraint, intimacy, confidence, exclusivity
- Visual language: large negative space, close-up materials, elegant asymmetry, slow reveal
- Layout signature: immersive hero, provenance story, product/editorial modules, appointment or concierge path
- Palette: warm ivory, ink, charcoal, metallic or jewel accent
- [Section compacted by Friday StitchPromptCompiler.]

Inspiration references:
- Quiet editorial luxury: Premium brands need restraint, materiality, white space, and concierge confidence. Must include: material detail, craft proof, concierge CTA. Avoid: coupon energy, crowded badges, loud gradients.
- Evidence-first product page: Visitors should see proof, workflow, and CTA before decorative storytelling. Must include: specific hero, proof objects, clear CTA. Avoid: stock-like hero, empty gradient panels, generic feature cards.
- Production int
- [Section compacted by Friday StitchPromptCompiler.]

Learned Friday memory rules:
- NEVER: Quality failure: desktop incoherent visible headline copy found. - Reject or fix this pattern before handoff: desktop: incoherent visible headline copy found.
- NEVER: Quality failure: desktop incoherent visible headline copy found. - Reject or fix this pattern before handoff: desktop: incoherent visible headline copy found.
- NEVER: Quality failure: Visible surfaces contain scaffold/generic copy Open workspace. - Reject or fix this pattern before hando
- [Section compacted by Friday StitchPromptCompiler.]

Output contract:
- Must return: a complete desktop screen/page, not a logo or isolated component
- Must return: semantic sections with readable visible copy
- Must return: responsive structure that can be converted to Next.js components
- Must return: all visible buttons and links named as real actions
- Must return: experience-mode evidence: canvas/scene, scroll behavior, product state transition, or a clear static-polished reason
- Minimum depth: 5 meaningful sections for a landing/website page
- Visible UI branding must use "Vale & Vellum" or a natural short form from the user request.
- The style profile name is internal implementation guidance; do not render NexusForge or other profile identifiers as visible UI copy unless the user explicitly asks for that brand.
- Reject if the design contains Home 1, Home 2, Service 1, Service 2, placeholder page-number artifacts, or generic scaffold copy.
- Normalize exaggerated Stitch scale: useful web layout
- [Section compacted by Friday StitchPromptCompiler.]

Design-system context:
- {"experience": {"allowed_modes": [{"id": "data_viz_motion", "implementation": ["charts", "maps", "timeline", "filters", "legend", "drill-down states"], "intent": "Use animated charts/maps/timelines to make data, trends, or operational state understandable.", "libraries": ["Recharts", "D3 optional", "Framer Motion optional"], "name": "Data Visualization Motion", "rejection_rules": ["Reject if charts are decorative, unlabeled, or unrelated to the domain."], "rules": [
- [Section compacted by Friday StitchPromptCompiler.]

Code/product signals:
- {"dependencies": [], "dev_dependencies": [], "existing_paths": [], "implementation_warning": "Use this as context for feasibility; do not render file paths or package metadata as visible UI copy.", "package_manager": "", "package_name": "", "project_root": "C:\\Users\\HomePC\\Desktop\\second-brain\\output\\stitch-vale-vellum-website", "scripts": {}, "stack": {"pages": ["home", "collections", "process", "inquiry"], "profile": "design_only_stitch_required", "surface": "marketing_website"}}

Handoff artifact rule:
- DESIGN.md, design-context.json, stitch-prompt.md, and site-design-system.json are source-of-truth handoff artifacts for Friday's implementation and critique loop.

Visual reference memory:
- Available approved assets: {}
- Usage rule: Use available references for composition, density, tone, and polish only; do not copy protected assets or render local file paths as UI copy.
- Missing-reference rule: If no approved local visual references exist, rely on brand_system, taxonomy, and output_contract rather than generic SaaS defaults.

## Guardrails
- Use Stitch SDK for UI exploration when configured; capture screenshots or exported HTML as evidence.
- Generate 2-3 design variants before accepting a direction when live design generation is approved.
- Score each variant against product/domain fit, user style memory, accessibility, copy quality, operational density, and frontend feasibility.
- Reject weak variants and convert only the highest-scoring accepted design into frontend implementation guidance.
- Use v0 only as a frontend-code fallback when a free allowance is verified.
- Use local style profiles and user style memory by default because they are free.
- Treat style profile names as internal implementation guidance; never render them as product branding unless the user requested that brand.
- Never accept generated design blindly; run browser, product-fit, UX/copy, accessibility, and dead-button gates.
