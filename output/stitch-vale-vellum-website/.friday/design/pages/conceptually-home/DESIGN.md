# DESIGN.md

Product: Vale & Vellum
Surface: marketing_website
Industry: luxury
Original request: Build a website design for Vale & Vellum, a boutique stationery and wedding invitation studio for couples, planners, and small luxury events. Use Friday's design-only workflow. Do not implement frontend code. Do not create a Next.js app. Save the Stitch design artifacts so the user can inspect the UI directly. Project goals: - Present Vale & Vellum as an elegant but modern paper studio, not a generic SaaS or template website. - Sell custom wedding invitation suites, event stationery, menus, place cards, wax seals, and concierge design packages. - Make the first viewport feel tactile, editorial, romantic, and premium without becoming beige and boring. - The site should support four pages conceptually: Home, Collections, Process, Inquiry. Generate the main website/homepage UI with enough content depth to imply the full site direction. Design direction: - Category: luxury / fashion-adjacent / editorial commerce. - Emotional feel: quiet romance, craft, ceremony, intimacy, precision, warm confidence. - Composition archetype: full-bleed editorial hero or image-led asymmetric editorial layout. Avoid the standard left-text/right-card SaaS hero. - Visual grammar: macro paper texture, foil impression, invitation stack, handwritten proof marks, refined serif headline, crisp sans labels, generous whitespace, tactile product details, restrained accent color. - Copy voice: specific, sensory, polished, never generic. Use language about paper stock, foil, letterpress, vellum wraps, hand assembly, planner deadlines, guest count, proof rounds, and concierge delivery. Required sections for the generated UI: 1. Hero with strong product signal: invitation suite / paper stack / tactile detail. It must not be hero-only; it should lead into content. 2. Collection preview: Signature Suites, Weekend Details, Bespoke Editorial, Planner Concierge. 3. Process: consultation, material direction, proofing, production, delivery. 4. Proof/credibility: production timelines, sample kit, planner-friendly deliverables, rush option. 5. Inquiry CTA with guest count / event date / package path. Rejection rules: - Reject generic SaaS dashboard cards, vague startup copy, empty dark sections, washed/blurry images, giant text that cuts off, one-section pages, placeholder menu labels like Home 1, Service 2, or lorem ipsum. - Do not use oversized rounded cards or a split hero with a fake analytics panel. - Do not make it dominated by beige alone; use a richer palette with ivory, ink, muted rose, deep olive, and foil/bronze accents. Brand name: Vale & Vellum. Page label: conceptually: Home. Route: /conceptually-home. Design the conceptually: Home page for Vale & Vellum. This is one page in a cohesive multi-page website. Page focus: brand, offer, proof, primary call to action. Site map: conceptually: Home (/conceptually-home); Collections (/collections); Process (/process); Inquiry (/inquiry). Visible logo and brand copy must say Vale & Vellum, not Vale & Vellum conceptually: Home. Do not render conceptually: Home as a giant eyebrow, standalone H1, numbered tab, or section title just because it is the route label. Do not label sections as Page 1, Home 1, Services 2, or similar numbered filler. Design only this route's page content; other pages should appear only as navigation links or short teasers where appropriate, never as repeated full sections. Use real route links from this site map (conceptually: Home (/conceptually-home); Collections (/collections); Process (/process); Inquiry (/inquiry)) rather than # placeholders or default routes that are not in the site map. Do not return only a logo, icon, brand mark, style guide, or isolated asset; return a complete page screen with navigation, main content, and footer. Keep the same design system across pages. Generate a complete page, not only a hero. Use production web proportions: desktop H1 around 40-58px, readable sections, no oversized whitespace, no sticky header overlap, no giant display type, and no decorative excess. Use structured sections that Friday can convert into Next.js routes without duplicating the hero.
Expanded request: Build a website design for Vale & Vellum, a boutique stationery and wedding invitation studio for couples, planners, and small luxury events. Use Friday's design-only workflow. Do not implement frontend code. Do not create a Next.js app. Save the Stitch design artifacts so the user can inspect the UI directly. Project goals: - Present Vale & Vellum as an elegant but modern paper studio, not a generic SaaS or template website. - Sell custom wedding invitation suites, event stationery, menus, place cards, wax seals, and concierge design packages. - Make the first viewport feel tactile, editorial, romantic, and premium without becoming beige and boring. - The site should support four pages conceptually: Home, Collections, Process, Inquiry. Generate the main website/homepage UI with enough content depth to imply the full site direction. Design direction: - Category: luxury / fashion-adjacent / editorial commerce. - Emotional feel: quiet romance, craft, ceremony, intimacy, precision, war...

## Brief Autopilot
- Active: False
- Vague prompt: False
- Style missing: False
- Product missing: False
- Assumption: The request includes a usable product/company signal; Friday expanded missing design details only.
- Clarifying question: What product/company should this website be for?
- Product/company type: luxury company website
- Target users: first-time visitors deciding whether to trust the product, high-intent private clients, collectors, concierge buyers, brand loyalists
- Page goal: Help visitors understand the product/company, trust it, inspect proof, and take a clear next step.
- Business model: premium direct-to-consumer or private inquiry sales
- Smart default: luxury_editorial_tactile
- Smart default reason: Luxury should signal scarcity, craft, and restraint before conversion pressure.
- Selected direction: cinematic_product_led
- Research status: live_research_complete
- Research query: luxury website design examples
- Research query: luxury customer needs website
- Research query: luxury landing page copy patterns
- Research query: luxury competitor website pricing positioning
- Research query: Vale & Vellum alternatives competitors
- Reject: Do not generate generic SaaS split-hero scaffolds unless the selected direction explicitly requires a split.
- Reject: Do not return a hero-only page; include enough below-fold content for the page goal.
- Reject: Do not use blurry, low-detail, darkened hero imagery as the main proof object.
- Reject: Do not use placeholder labels such as Home 1, Service 2, feature one, lorem ipsum, or vague startup filler.
- Reject: Do not implement the first generated design blindly; critique it before code.
- Reject: Do not use loud gradients, badge-heavy SaaS cards, discount language, or cluttered grids.
- Critique check: Is the UI genuinely beautiful or at least professionally polished for the chosen category?
- Critique check: Is the first viewport strong, specific, and not a generic SaaS split hero?
- Critique check: Is imagery crisp and meaningful enough to inspect, not blurry/washed-out decoration?
- Critique check: Is there enough content depth beyond the hero for the page/screen goal?
- Critique check: Is the copy original, product-specific, and free of scaffold filler?
- Critique check: Does the design match the product category and selected creative direction?
- Critique check: Can Friday implement the design into real routes/components without dead controls?

## Intent
- Goal: Help visitors understand Vale & Vellum, trust the offer, compare the value, and take the next step without generic filler or oversized brochure sections.
- Audience: first-time visitors deciding whether to trust the product, high-intent private clients, collectors, concierge buyers, brand loyalists
- Emotional feel: desire, restraint, intimacy, confidence, exclusivity
- Message: The brand is scarce, crafted, and worth slowing down for.

## Creative Brief
- One-sentence feel: Vale & Vellum should feel like quiet luxury with editorial restraint and tactile detail.
- Decision moment: A high-intent private client is deciding whether the brand feels rare, crafted, and worthy of a personal inquiry.
- Primary objection: The experience can feel mass-market, loud, or insufficiently premium.
- Design answer: Use restraint, material detail, provenance, appointment paths, and quiet confidence instead of badges or discounts.
- Trust signals: craft proof, provenance, atelier detail, private appointment, concierge access

## Composition
- Archetype: Full-Bleed Media Hero
- Rationale: Physical, visual, luxury, fashion, construction, real estate, and story-led brands need place, material, or people to carry the first impression.
- Alternative archetype: Full-Bleed Media Hero: Full-bleed image, video, rendered scene, or strong visual background with text anchored directly on the media, not inside a floating card.
- Alternative archetype: Workflow Stage: Problem state, AI/action state, approval/audit state, and outcome are staged as one product workflow.
- Alternative archetype: Editorial Asymmetric: Asymmetric headline, image crop, metadata, and proof arranged like a designed editorial spread.
- Alternative archetype: Centered Statement Hero: Centered or left-anchored headline over a quiet background system, with CTAs and the next proof section peeking into view.
- Alternative archetype: Split Product Proof: Two-column hero is allowed only when the right side carries real proof: UI, code, map, product, case image, or workflow state.
- Composition rule: Choose the composition before visual styling; colors and cards must not be the main differentiator.
- Composition rule: Do not default to a left-text/right-card split hero unless Split Product Proof is the selected archetype.
- Composition rule: Each generated variant must change the first viewport structure, not just copy, palette, or card styling.
- Composition rule: If the archetype uses media or a scene, the media must carry real product/domain meaning.
- Composition rule: For visual/physical brands, use image, material, scene, or place as the first-viewport evidence.
- First viewport: Use the Full-Bleed Media Hero composition archetype: Full-bleed image, video, rendered scene, or strong visual background with text anchored directly on the media, not inside a floating card.
- First viewport: Brand and navigation must identify Vale & Vellum clearly without visible internal profile labels.
- First viewport: The first viewport must expose the next meaningful section; do not end at a blank hero.
- First viewport: Every visible proof object must be domain-specific, not a decorative placeholder.
- First viewport: Use real-feeling media, image, material, site, or scene as the hero background with text anchored over it, not trapped in a card.
- Layout depth: Generate multiple sections with different rhythm; do not repeat the same card grid after the hero.
- Layout depth: Variant explorations must change composition archetype or first-viewport structure, not just palette or copy.
- Layout depth: Normalize exaggerated Stitch scale during implementation so headings, sections, and buttons fit real desktop and mobile viewports.
- Layout depth: Use 5 to 7 meaningful sections in a single landing page or page-specific depth for multi-page sites.
- Layout depth: Every section should have a job: explain, prove, compare, qualify, transact, or convert.
- Visual hierarchy: Composition comes before styling. H1 should be strong but not viewport-breaking; proof must be visible, inspectable, and domain-specific.
- Responsive notes: On mobile, maintain readable type, no overlapping text, and clear CTA order.
- Variant policy: Ask Stitch for compositionally different variants; reject same split-hero/card rhythm unless it is explicitly selected and well justified.

## Experience Mode
- Mode: Data Visualization Motion
- Intent: Use animated charts/maps/timelines to make data, trends, or operational state understandable.
- Recommended libraries: Recharts, D3 optional, Framer Motion optional
- Alternative mode: Data Visualization Motion: Use animated charts/maps/timelines to make data, trends, or operational state understandable.
- Alternative mode: Editorial Luxury: Create a premium, art-directed experience with restraint, asymmetry, tactile imagery, and slow confidence.
- Alternative mode: Cinematic Scroll: Use scroll progression, layered sections, pinned moments, and reveal timing to tell a product or brand story.
- Alternative mode: Parallax Story: Use depth, foreground/background motion, and anchored content to create visual drama without requiring full 3D.
- Alternative mode: Static Polished: Ship a refined, fast, content-led interface where hierarchy, copy, imagery, and spacing carry the experience.
- Implementation: charts
- Implementation: maps
- Implementation: timeline
- Implementation: filters
- Implementation: legend
- Implementation: drill-down states
- Implementation: Tie every animated state to a real product, workflow, chart, map, command, or action.
- Motion rule: Animation should support data comprehension, not obscure values.
- Motion rule: Use accessible labels, legends, and tabular alternatives where possible.
- Motion rule: Avoid fake meaningless charts.
- Motion rule: Pick interaction libraries from the mode; do not add heavy animation libraries unless the mode benefits from them.
- Motion rule: Every motion/3D/parallax effect must have a user-facing purpose and a reduced-motion or fallback path.
- Motion rule: Friday implementation must verify screenshots, responsiveness, interaction smoke, and performance before claiming visual quality.
- Verification: chart rendering check
- Verification: label/legend check
- Verification: browser screenshot
- Verification: performance budget
- Reject if: Reject if charts are decorative, unlabeled, or unrelated to the domain.
- Fallback: Fallback is normal responsive semantic content.
- Performance: {"rule": "prioritize Core Web Vitals, readable layout, and fast interaction feedback"}

## Brand System
- Logo direction: quiet wordmark for Vale & Vellum; refined spacing, no loud badge
- Typography: {"body": "clean readable sans", "display": "editorial serif or high-contrast display", "mono": "not primary"}
- Color tokens: {"accent": "#9f6b3e", "accent_2": "#2f2924", "bg": "#f7f1e8", "border": "#ded2c3", "danger": "#9f1239", "muted": "#71675e", "success": "#3f6f53", "surface": "#fffaf3", "surface_2": "#14110f", "text": "#17120d", "warning": "#b7791f"}
- Spacing scale: {'xs': '4px', 'sm': '8px', 'md': '16px', 'lg': '24px', 'xl': '40px', 'section': '72px desktop / 44px mobile'}
- Radius system: 0px to 6px; editorial, not pill-heavy
- Icon style: minimal marks; use icons sparingly
- Motion style: slow, restrained reveals; no bouncy UI

## Taxonomy Guidance
- Message: The brand is scarce, crafted, and worth slowing down for.
- Emotional feel: desire, restraint, intimacy, confidence, exclusivity
- Visual grammar:
- Copy voice: spare, sensorial, confident, never loud

## Visual Grammar
- Direction: quiet luxury with editorial restraint and tactile detail
- Language: large negative space, close-up materials, elegant asymmetry, slow reveal
- Layout: immersive hero, provenance story, product/editorial modules, appointment or concierge path
- Palette: warm ivory, ink, charcoal, metallic or jewel accent used sparingly
- Typography: refined serif or high-contrast display paired with quiet readable body type
- Imagery: macro product details, craftsmanship, architecture, human service moments
- Interaction: concierge CTAs, appointment flows, lookbook navigation, restrained micro-interactions
- Copy voice: spare, sensorial, confident, never loud

## Content Model
- Navigation: conceptually: Home, Collections, Process, Inquiry
- Primary CTAs: Request concierge access, Explore collection
- Required sections: global navigation, brand-specific hero, trust/proof teaser, service teaser, primary contact CTA
- Proof objects: client proof, process step, result metric, response promise
- Domain terms: vale, vellum, boutique, stationery, wedding, invitation, studio, couples, planners, small, luxury, events, friday's, design-only, save, user, inspect, directly

## Section Blueprint
- Hero: Create desire with brand, material detail, and a discreet action. Must show: brand statement, hero image, concierge CTA.
- Provenance: Show why the object/service is rare and credible. Must show: craft, materials, heritage.
- Collection or offer: Let the visitor inspect options without ecommerce clutter. Must show: collection, fit, scarcity.
- Concierge path: Make the next step private and high-touch. Must show: appointment, inquiry, response promise.

## Copy Bank
- Headline direction: Crafted for private clients who notice the difference.
- Headline direction: A quieter standard of luxury, made visible.
- Headline direction: Objects and experiences with provenance.
- Subhead direction: Vale & Vellum should communicate The brand is scarce, crafted, and worth slowing down for. in a spare, sensorial, confident, never loud voice.
- Microcopy: Request concierge access, View the collection, Private appointment
- Words to use: vale, vellum, boutique, stationery, wedding, invitation, studio, couples, planners, small, luxury, events, craft proof, provenance, atelier detail, private appointment
- Words to avoid: discount, deal, limited-time offer, all-in-one solution, Home 1, Service 1, lorem ipsum, smarter operations

## Component Inventory
- chart/map/timeline surface
- legend and labels
- data filter controls
- editorial hero
- material image field
- provenance cards
- lookbook modules
- concierge inquiry form

## Output Contract
- Must return: a complete desktop screen/page, not a logo or isolated component
- Must return: semantic sections with readable visible copy
- Must return: responsive structure that can be converted to Next.js components
- Must return: all visible buttons and links named as real actions
- Must return: experience-mode evidence: canvas/scene, scroll behavior, product state transition, or a clear static-polished reason
- Minimum depth: 5 meaningful sections for a landing/website page
- Reject if: the first viewport is mostly blank space
- Reject if: hero text is clipped or too large for the viewport
- Reject if: copy contains numbered artifacts like Home 1 or Service 2
- Reject if: layout looks like a generic SaaS scaffold unrelated to the industry
- Reject if: all variants reuse the same left-text/right-card hero structure without a composition-specific reason
- Reject if: design cannot be implemented without a giant one-file blob

## Variant Briefs
- Variant 1: Editorial luxury lookbook with immersive imagery, provenance, and discreet concierge action. Use or reinterpret the Full-Bleed Media Hero composition archetype with the Data Visualization Motion experience mode. Change first-viewport structure, motion/interaction strategy, proof object placement, and section emphasis. Do not only change colors.
- Variant 2: Boutique product story with material close-ups, collection modules, and appointment path. Use or reinterpret the Workflow Stage composition archetype with the Editorial Luxury experience mode. Change first-viewport structure, motion/interaction strategy, proof object placement, and section emphasis. Do not only change colors.
- Variant 3: Private-client service page with restrained typography, trust cues, and high-touch contact flow. Use or reinterpret the Editorial Asymmetric composition archetype with the Cinematic Scroll experience mode. Change first-viewport structure, motion/interaction strategy, proof object placement, and section emphasis. Do not only change colors.

## Inspiration Directions
- Quiet editorial luxury: Premium brands need restraint, materiality, white space, and concierge confidence.
- Evidence-first product page: Visitors should see proof, workflow, and CTA before decorative storytelling.
- Production interface handoff: The design must convert into real components, not a static poster.

## Visual Reference Memory
- Available: False
- Usage rule: Use available references for composition, density, tone, and polish only; do not copy protected assets or render local file paths as UI copy.

## Learned Friday Memory Rules
- Available: True
- Summary: 10 learned rule(s) selected for this request.
- NEVER: Quality failure: desktop incoherent visible headline copy found. - Reject or fix this pattern before handoff: desktop: incoherent visible headline copy found.
- NEVER: Quality failure: desktop incoherent visible headline copy found. - Reject or fix this pattern before handoff: desktop: incoherent visible headline copy found.
- NEVER: Quality failure: Visible surfaces contain scaffold/generic copy Open workspace. - Reject or fix this pattern before handoff: Visible surfaces contain scaffold/generic copy: Open workspace.
- NEVER: Quality failure: Visible surfaces contain scaffold/generic copy Open workspace. - Reject or fix this pattern before handoff: Visible surfaces contain scaffold/generic copy: Open workspace.
- NEVER: Quality failure: Visible surfaces contain scaffold/generic copy Open workspace. - Reject or fix this pattern before handoff: Visible surfaces contain scaffold/generic copy: Open workspace.
- NEVER: Quality failure: desktop developer-tools hero uses stock/person portrait imagery. - Reject or fix this pattern before handoff: desktop: developer-tools hero uses stock/person portrait imagery.
- NEVER: Quality failure: Visible surfaces contain scaffold/generic copy Open workspace. - Reject or fix this pattern before handoff: Visible surfaces contain scaffold/generic copy: Open workspace.
- NEVER: Quality failure: Visible surfaces contain scaffold/generic copy Open workspace. - Reject or fix this pattern before handoff: Visible surfaces contain scaffold/generic copy: Open workspace.
- NEVER: Quality failure: Visible surfaces contain scaffold/generic copy Open workspace. - Reject or fix this pattern before handoff: Visible surfaces contain scaffold/generic copy: Open workspace.
- NEVER: Quality failure: desktop developer-tools hero uses stock/person portrait imagery. - Reject or fix this pattern before handoff: desktop: developer-tools hero uses stock/person portrait imagery.

## Site Continuity
- Page label: Conceptually Home
- Site design system path: C:\Users\HomePC\Desktop\second-brain\output\stitch-vale-vellum-website\.friday\design\site-design-system.json
- Use this shared site design system for every page in the same website.
- Do not let per-page Stitch generations drift in typography, palette, navigation, button style, or brand voice.
- Each page may change layout emphasis, but must preserve the global brand system and navigation model.

## Design Rules
- Scale: Use restrained production UI scale: no oversized headings that exceed one viewport, no decorative empty whitespace, and no section taller than its useful content.
- Screen: Produce a complete desktop web page with header/navigation, main content, page-specific sections, conversion action, and footer; do not return only a logo, icon, brand mark, or design-system asset.
- Implementation: Friday may adapt spacing, typography, and layout for Next.js implementation; do not copy exaggerated Stitch scale literally.
- Page labels: Do not render page labels as giant hero eyebrows, standalone H1 text, or numbered section names.
- Normalization: Stitch may exaggerate scale; Friday must normalize typography, spacing, and viewport height during Next.js implementation.
- Avoid: Do not use generic SaaS dashboard imagery for a non-SaaS company website.
- Avoid: Do not use huge empty hero sections or headings that consume the viewport.
- Avoid: Do not repeat page labels as section titles.
- Avoid: Do not use placeholder copy, raw prompts, debug labels, or Friday proof language.
- Avoid: Do not rely on only beige/cream cards unless the domain truly calls for it.
- Avoid: Do not use loud gradients, badge-heavy SaaS cards, discount language, or cluttered grids.

## Design-System Memory
- Profile: NexusForge Next.js
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

## Handoff Requirements
- Generate design variants first; frontend implementation may use only the selected accepted handoff.
- Preserve the design intent, but normalize exaggerated Stitch scale for usable web/mobile viewports.
- Friday may adapt spacing, typography, and layout for Next.js implementation; do not copy exaggerated Stitch scale literally.
- Run Playwright/browser screenshot review after implementation.
- Reject output with dead buttons, broken navigation, placeholder copy, route-label headings, or internal profile-name leaks.
- Style rule: Use src/app only for routes, layouts, route handlers, and route-local boundaries.
- Style rule: Put real feature UI in src/components/<FeatureName>.
- Style rule: Put generic primitives in src/components/ui.
- Style rule: Put navigation and shell components in src/components/layout.
- Style rule: Put API clients and response normalization in src/services.
- Style rule: Put shared browser state in src/store.
- Style rule: Put reusable client workflows in src/hooks.
- Style rule: Put domain helpers, utilities, security helpers, and product contracts in src/lib.
