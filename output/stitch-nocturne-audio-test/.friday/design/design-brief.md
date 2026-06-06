# Design Provider Plan

Product: Nocturne Audio
Request: Build a cinematic luxury landing page for Nocturne Audio, a premium spatial-audio headphone brand. It should feel immersive, tactile, nocturnal, editorial, and product-led. The first viewport should not be a generic split SaaS hero. Prefer a full-bleed product/media hero or immersive scene with the headphone as the first-viewport signal, with refined launch copy, product close-up moments, soundstage proof, creator testimonials, and a conversion path for preorders. Use rich dark materials, controlled contrast, precise typography, and subtle motion direction; avoid generic dashboard cards, operations copy, backend/Web3 language, and bland business-consulting phrasing.

## Provider Policy
- Stitch: ready - Stitch SDK is configured for UI design generation.
- v0: blocked - Set V0_API_KEY only if you want Friday to use v0.
- Local style memory: ready - Local style profiles are file/database memory and do not require paid API calls.

## Style Memory
- Profile: NexusForge Next.js

## Design Contract
- Page: home
- Objective: Design a complete product landing page with anchor-style navigation, product proof, conversion actions, and section depth. This is one cohesive page, not a dashboard screen and not a multi-page website index.
- Required sections: global navigation, brand-specific hero, proof/status strip, problem-to-solution, core capabilities, how it works, primary CTA/footer
- Scale rule: Use restrained production UI scale: no oversized headings that exceed one viewport, no decorative empty whitespace, and no section taller than its useful content.

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
- Product goal: Help visitors understand Nocturne Audio, trust the offer, compare the value, and take the next step without generic filler or oversized brochure sections.
- Target audience: first-time visitors deciding whether to trust the product, high-intent private clients, collectors, concierge buyers, brand loyalists
- Emotional intent: desire, restraint, intimacy, confidence, exclusivity
- Core message: The brand is scarce, crafted, and worth slowing down for.
- Inspiration direction: Quiet editorial luxury: Premium brands need restraint, materiality, white space, and concierge confidence.
- Inspiration direction: Evidence-first product page: Visitors should see proof, workflow, and CTA before decorative storytelling.
- Inspiration direction: Production interface handoff: The design must convert into real components, not a static poster.
- Learned rules: 10 learned rule(s) selected for this request.
- Context artifacts: design-context.json, DESIGN.md, stitch-prompt.md, and site-design-system.json
- Stitch prompt compilation: 11578/12000 chars

## Stitch Prompt

Design context package:
- Critical rejection rule: Do not use generic SaaS dashboard imagery for a non-SaaS company website.
- Domain copy guardrail: Never let internal prompt labels, route labels, or scaffold phrases become visible product copy.
- User intent: Build a cinematic luxury landing page for Nocturne Audio, a premium spatial-audio headphone brand. It should feel immersive, tactile, nocturnal, editorial, and product-led. The first viewport should not be a generic split SaaS hero. Prefer a full-bleed product/media hero or immersive scene with the headphone as the first-viewport signal, with refined launch copy, product close-up moments, soundstage proof, creator testimonials, and a conversion path for preorders. Use rich dark materials, controlled contrast, pr...
- Product goal: Help visitors understand Nocturne Audio, trust the offer, compare the value, and take the next step without generic filler or oversized brochure sections.
- Emotional intent: desire, restraint, intimacy, confidence, exclusivity
- Cor
- [Section compacted by Friday StitchPromptCompiler.]

Creative brief:
- One-sentence feel: Nocturne Audio should feel like quiet luxury with editorial restraint and tactile detail.
- Decision moment: A high-intent private client is deciding whether the brand feels rare, crafted, and worthy of a personal inquiry.
- Primary objection to overcome: The experience can feel mass-market, loud, or insufficiently premium.
- Design answer: Use restraint, material detail, provenance, appointment paths, and quiet confidence instead of badges or discounts.
- Trust signals to make visible: craft proof, provenance, atelier detail, private appointment, concierge access

Concrete page composition:
- Composition archetype: Full-Bleed Media Hero
- Archetype rationale: Physical, visual, luxury, fashion, construction, real estate, and story-led brands need place, material, or people to carry the first impression.
- Allowed alternative archetype: Full-Bleed Media Hero: Full-bleed image, video, rendered scene, or strong visual background with text anchored directly on the media, not inside a floating card.
- Allowed alternative archetype: Immersive Scene: Full-viewport scene or animated visual world with concise action copy, platform/action buttons, and visible gameplay or interaction cues.
- Allowed alternative archetype: Editorial Asymmetric: Asymmetric headline, image crop, metadata, and proof arranged like a designed editorial spread.
- Allowed alternative archetype: Centered Statement Hero: Centered or left-anchored headline over a quiet background system, with CTAs and the next proof section peeking into view.
- Composition rule: Choose the composition before visual styling; colors and cards must not be the main differentiator.
- Composition rule: Do not default to a left-text/right-card split hero
- [Section compacted by Friday StitchPromptCompiler.]

Experience mode and motion/3D contract:
- Experience mode: Interactive 3D
- Intent: Use a real 3D scene as the primary product/brand signal, with interaction and motion that reveals meaning.
- Recommended libraries: Three.js, @react-three/fiber, @react-three/drei, Framer Motion optional
- Allowed alternate mode: Interactive 3D: Use a real 3D scene as the primary product/brand signal, with interaction and motion that reveals meaning.
- Allowed alternate mode: Cinematic Scroll: Use scroll progression, layered sections, pinned moments, and reveal timing to tell a product or brand story.
- Allowed alternate mode: Product Demo Motion: Show how the product changes state: before, action, approval, result, and proof.
- Allowed alternate mode: Editorial Luxury: Create a premium, art-directed experience with restraint, asymmetry, tactile imagery, and slow confidence.
- Implementation note: full-bleed canvas
- Implementation note: camera/framing
- Implementation note: lighting
- Implementation note: interactive object states
- Implementation note: fallback image/static path
- Implementation note: Use a visible canvas/WebGL or scene layer only
- [Section compacted by Friday StitchPromptCompiler.]

Section-by-section blueprint:
- Hero: Create desire with brand, material detail, and a discreet action. Must show: brand statement, hero image, concierge CTA. Visual objects: editorial hero, material close-up.
- Provenance: Show why the object/service is rare and credible. Must show: craft, materials, heritage. Visual objects: story panel, detail modules.
- Collection or offer: Let the visitor inspect options without ecommerce clutter. Must show: collection, fit, scarcity. Visual objects: lookbook grid, product cards.
- Concierge path: Make the next step private and high-touch. Must show: appointment, inquiry, response promise. Visual objects: concierge form, contact strip.

Component inventory to design:
- full-bleed scene/canvas surface
- scene fallback poster/content
- reduced-motion controls
- editorial hero
- material image field
- provenance cards
- lookbook modules
- concierge inquiry form

Copy and content requirements:
- Navigation: Atelier, Collections, Process, Concierge
- Primary CTAs: Request concierge access, Explore collection
- Proof objects: client proof, process step, result metric, response promise
- Headline directions: Crafted for private clients who notice the difference. / A quieter standard of luxury, made visible. / Objects and experiences with provenance.
- Subhead direction: Nocturne Audio should communicate The brand is scarce, crafted, and worth slowing down for. in a spare, sensorial, confident, never loud voice.
- Microcopy examples: Request concierge access, View the collection, Private appointment
- Words to use: cinematic, luxury, landing, nocturne, audio, premium, spatial-audio, headphone, should, feel, immersive, tactile, craft proof, provenance, atelier detail, private appointment
- Words to avoid: discount, deal
- [Section compacted by Friday StitchPromptCompiler.]

Brand system:
- Logo direction: quiet wordmark for Nocturne Audio; refined spacing, no loud badge
- Typography pair: {"body": "clean readable sans", "display": "editorial serif or high-contrast display", "mono": "not primary"}
- Color tokens: {"accent": "#9f6b3e", "accent_2": "#2f2924", "bg": "#f7f1e8", "border": "#ded2c3", "danger": "#9f1239", "muted": "#71675e", "success": "#3f6f53", "surface": "#fffaf3", "surface_2": "#14110f", "text": "#17120d", "warning": "#b7791f"}
- Spacing scale: {'xs': '4px', 'sm': '8px', 'md': '16px', 'lg': '24px', 'xl': '40px', 'section': '72px desktop / 44px mobile'}
- Radius system: 0p
- [Section compacted by Friday StitchPromptCompiler.]

Visual grammar:
- Art direction: quiet luxury with editorial restraint and tactile detail
- Message: The brand is scarce, crafted, and worth slowing down for.
- Emotional feel: desire, restraint, intimacy, confidence, exclusivity
- Visual language: large negative space, close-up materials, elegant asymmetry, slow reveal
- Layout signature: immersive hero, provenance story, product/editorial modules, appointment or concierge path
- Palette: warm ivory, ink, charcoal, metallic or jewel accent used sparingly
- Typography: refined serif or high-contrast display paired with quiet readable body type
- Imagery: macro prod
- [Section compacted by Friday StitchPromptCompiler.]

Inspiration references:
- Quiet editorial luxury: Premium brands need restraint, materiality, white space, and concierge confidence. Must include: material detail, craft proof, concierge CTA. Avoid: coupon energy, crowded badges, loud gradients.
- Evidence-first product page: Visitors should see proof, workflow, and CTA before decorative storytelling. Must include: specific hero, proof objects, clear CTA. Avoid: stock-like hero, empty gradient panels, generic feature cards.
- Production interface handoff: The design must convert into real components, not a static poster. Must include: semantic sections, responsive
- [Section compacted by Friday StitchPromptCompiler.]

Learned Friday memory rules:
- NEVER: Quality failure: Visible surfaces contain scaffold/generic copy Launch readiness. - Reject or fix this pattern before handoff: Visible surfaces contain scaffold/generic copy: Launch readiness.
- NEVER: Quality failure: Visible surfaces contain scaffold/generic copy Launch readiness. - Reject or fix this pattern before handoff: Visible surfaces contain scaffold/generic copy: Launch readiness.
- NEVER: Quality failure: Visible surfaces contain scaffold/generic copy Launch readiness. - Reject or fix this pattern before handoff: Visible surfaces contain scaffold/generic copy: Launc
- [Section compacted by Friday StitchPromptCompiler.]

Output contract:
- Must return: a complete desktop screen/page, not a logo or isolated component
- Must return: semantic sections with readable visible copy
- Must return: responsive structure that can be converted to Next.js components
- Must return: all visible buttons and links named as real actions
- Must return: experience-mode evidence: canvas/scene, scroll behavior, product state transition, or a clear static-polished reason
- Minimum depth: 5 meaningful sections for a landing/website page
- Visible UI branding must use "Nocturne Audio" or a natural short form from the user request.
- The style profile name is internal implementation guidance; do not render NexusForge or other profile identifiers as visible UI copy unless the user explicitly asks for that brand.
- Reject if the design contains Home 1, Home 2, Service 1, Service 2, placeholder page-number artifacts, or generic scaffold copy.
- Normalize exaggerated Stitch scale: useful web layout beats poster-sized type.
- Reject if: the first viewport is mostly blank space
- Reject if: hero text is clipped or too large for the viewport
- Reject if: copy contains numbered artifacts like Home 1 or Service 2
- Reject if: la
- [Section compacted by Friday StitchPromptCompiler.]

Design-system context:
- {"experience": {"allowed_modes": [{"id": "interactive_3d", "implementation": ["full-bleed canvas", "camera/framing", "lighting", "interactive object states", "fallback image/static path"], "intent": "Use a real 3D scene as the primary product/brand signal, with interaction and motion that reveals meaning.", "libraries": ["Three.js", "@react-three/fiber", "@react-three/drei", "Framer Motion optional"], "name": "Interactive 3D", "rejection_rules": ["Reject if canvas is blank, tiny, hidden, decorative only, or breaks mobile layout."], "rules": ["The 3D canvas must be visible, nonblank, framed,
- [Section compacted by Friday StitchPromptCompiler.]

Code/product signals:
- {"dependencies": [], "dev_dependencies": [], "existing_paths": [], "implementation_warning": "Use this as context for feasibility; do not render file paths or package metadata as visible UI copy.", "package_manager": "", "package_name": "", "project_root": "C:\\Users\\HomePC\\Desktop\\second-brain\\output\\stitch-nocturne-audio-test", "scripts": {}, "stack": {"label": "Next.js web app", "stack": "nextjs"}}

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
