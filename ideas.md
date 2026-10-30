# Design Direction — Campus AI Attendance

## Direction source
The user specified a **premium modern AI college attendance dashboard** with a dark-blue professional theme, glassmorphism, modern typography, responsiveness, sidebar and top navigation, dashboard cards, smooth hover animations, rounded components, subtle shadows, clean spacing, modern buttons, responsive tables and mobile support. This is the chosen direction; do not introduce a competing aesthetic.

## Design dimensions
- **Design movement:** contemporary enterprise dashboard with restrained glass surfaces, not a generic Django admin theme.
- **Core principles:** data clarity first; calm institutional professionalism; strong contrast; visible active state; every control maps to a real action; responsive layouts keep key workflows usable on a phone.
- **Color philosophy:** deep ink/navy background and navy panels; cool blue/teal accents for active navigation and camera focus; green for success/present; amber for already-marked/warnings; warm red for errors; muted gray-blue text for secondary information.
- **Layout paradigm:** persistent left rail on desktop, compact top bar, flexible main content grid; cards for high-level statistics, wide responsive data tables, and a focused camera panel with a face guide. Collapse the rail and reflow the grid for mobile.
- **Signature elements:** small campus/face-check product mark, fine cool-blue borders, layered low-contrast glass surfaces, subtle corner radii and restrained scan-line/focus framing around the actual video image.
- **Interaction philosophy:** clear states and feedback; camera access begins only after the user activates it; explicit permission/errors; safe confirmation for destructive student deletion; CSRF-protected state changes; no decorative-only buttons.
- **Animation:** short, low-amplitude hover/focus transitions; avoid motion during face scanning and respect reduced-motion preferences.
- **Typography system:** system UI sans-serif stack for fast loading and reliable Unicode; larger semibold dashboard numbers; compact uppercase stat labels; highly legible table text.
- **Brand essence:** trustworthy, practical, privacy-conscious campus operations.
- **Brand voice:** concise, direct, respectful and helpful, especially for recognition/camera errors.
- **Wordmark/logo:** compact “Campus AI Attendance” wordmark in the sidebar beside a simple attendance/face-scan symbol; the same mark is used as the favicon and platform project icon.
- **Signature brand color:** cool electric teal against deep navy, balanced with accessible contrast.

## Asset scope
This is an internal/admin dashboard. No stock or decorative imagery is needed. Create only the required distinct project icon: an opaque, unmasked square PNG with full-bleed navy background, broad flat shapes, a strong abstract camera/facial-attendance silhouette, generous negative space, and no text or small details. Reuse the mark in the header and favicon.
