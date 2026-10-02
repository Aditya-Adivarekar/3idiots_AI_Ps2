---
name: Civic Warmth & Clarity
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#43474d'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#74777e'
  outline-variant: '#c3c6ce'
  surface-tint: '#49607c'
  primary: '#001428'
  on-primary: '#ffffff'
  primary-container: '#0f2942'
  on-primary-container: '#7991af'
  inverse-primary: '#b0c9e8'
  secondary: '#904d00'
  on-secondary: '#ffffff'
  secondary-container: '#fe932c'
  on-secondary-container: '#663500'
  tertiary: '#00170d'
  on-tertiary: '#ffffff'
  tertiary-container: '#002e1d'
  on-tertiary-container: '#21a173'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d1e4ff'
  primary-fixed-dim: '#b0c9e8'
  on-primary-fixed: '#011d35'
  on-primary-fixed-variant: '#314863'
  secondary-fixed: '#ffdcc3'
  secondary-fixed-dim: '#ffb77d'
  on-secondary-fixed: '#2f1500'
  on-secondary-fixed-variant: '#6e3900'
  tertiary-fixed: '#85f8c4'
  tertiary-fixed-dim: '#68dba9'
  on-tertiary-fixed: '#002114'
  on-tertiary-fixed-variant: '#005137'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-xl:
    fontFamily: Noto Sans
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 52px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Noto Sans
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 38px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Noto Sans
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Noto Sans
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
  headline-md:
    fontFamily: Noto Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Noto Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  title-lg:
    fontFamily: Noto Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
  title-md:
    fontFamily: Noto Sans
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Noto Sans
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Noto Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Noto Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-lg:
    fontFamily: Noto Sans
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
  label-md:
    fontFamily: Noto Sans
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Noto Sans
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.25rem
  gutter-mobile: 0.75rem
  gutter-desktop: 1.5rem
  margin: 1.25rem
  margin-mobile: 1rem
  margin-desktop: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

The brand personality is civic, empathetic, and profoundly reassuring. It bridges the gap between complex constitutional welfare architecture and first-generation digital citizens, low-literacy users, rural parents, and ambitious students across India. The experience strips away bureaucratic intimidation, cold tabular portals, and obtuse legalese, replacing them with warmth, absolute transparency, and dignity.

The design movement combines **Contemporary Civic Humanism** with **Tactile Functionalism**. It avoids cold enterprise sterility and Silicon Valley minimalism in favor of grounded, physical-world cues: parchment-tinted surfaces, generous padding that honors imperfect touch precision, high-contrast semantic indicators, and clear visual signposting. The emotional response is one of safety, empowerment, and clarity—transforming the overwhelming process of government scheme discovery into a supportive, conversational journey.

## Colors

The color system draws from a respectful, civic-inspired palette tailored for high-glare outdoor screens, low-cost displays, and multi-tier cognitive states.

- **Primary (`#0F2942`)**: Deep Indigo / Ashoka Navy. Conveys statutory authority, grounding, and civic trust without the cold detachment of pure black or stark primary blue. Used for primary interactive actions, high-emphasis text, and core structural navigation.
- **Secondary (`#D97706`)**: Warm Saffron / Amber Ochre. Used for attention-demanding items, action reminders, warnings, critical eligibility deadlines, and application status notices. Evokes optimism, urgency, and civic vitality without inducing panic.
- **Tertiary (`#059669`)**: Gentle Forest Jade. Denotes absolute eligibility, verified documents, successful disbursement statuses, and positive outcomes. Paired with a soft green wash (`#ECFDF5`) for container backgrounds to reduce visual fatigue.
- **Neutral (`#64748B`)**: Balanced Slate. Governs secondary metadata, inactive borders, unverified states, and supporting labels. 
- **Destructive / Ineligible (`#DC2626`)**: Soft Terracotta Red. Indicates ineligibility, rejected forms, or expired schemes with dignity and calm, avoiding abrasive neon reds.
- **Canvas & Surfaces**: The base canvas uses `#FAF8F5` (Warm Cream / Khadi White) with component cards set on `#FFFFFF`, providing natural, organic contrast that mitigates harsh digital glare for rural and field-use environments.

## Typography

Noto Sans serves as the single typographic anchor across Latin, Devanagari, and pan-Indian scripts. It provides typographic parity: font metrics, optical heights, and stroke weights align across Hindi, Marathi, Bengali, Tamil, Telugu, and English, eliminating clipping and awkward reflows during dynamic language switching.

- **Legibility Rules**: Base body text is never smaller than `16px` (`body-md`) for standard interactive copy and user instructions to accommodate varying eyesight, low-resolution phone displays, and older family members.
- **Line Heights**: Set deliberately tall (`1.5` to `1.6x` ratio) to give breathing room to Devanagari conjuncts, *matras* (diacritical marks), and complex vowel signs.
- **Numbers & Metrics**: Benefit amounts (e.g., ₹25,000/वर्ष) use `headline-sm` or `headline-md` with `font-weight: 700` to make financial grants instantly parseable without reading dense text blocks.

## Layout & Spacing

The layout is built on a responsive fluid grid that prioritizes single-column scanning on mobile devices and structured modular card grids on desktop displays.

- **Mobile (< 640px)**: 4 columns with `margin-mobile` (1rem / 16px) and `gutter-mobile` (0.75rem / 12px). Content cards, benefit trackers, and questionnaire wizard steps stretch full width.
- **Tablet (640px – 1024px)**: 8 columns with 1.25rem (20px) gutters and margins. Split-screen layout paired with visual scheme summaries.
- **Desktop (> 1024px)**: 12 columns with a max content container of `1200px` centered on the viewport. Gutters expand to `gutter-desktop` (1.5rem / 24px) and outer margins to `margin-desktop` (2rem / 32px).
- **Rhythm & Touch Targets**: Spacing between unrelated card groups follows `space-xl` (2.5rem). The standard touch area for any actionable element maintains an absolute minimum hit target of `48px × 48px`, accompanied by `space-sm` or `space-md` gaps to prevent accidental taps on low-end capacitive screens.

## Elevation & Depth

This design system avoids harsh floating drop shadows or heavy blur layers that degrade rendering performance on budget Android devices. Instead, it creates depth and clear interactive affordance using **Tonal Layering** accompanied by **Subtle Warm Ambient Shadows**.

- **Canvas (Level 0)**: `#FAF8F5`. Flat background with zero elevation.
- **Resting Card / Container (Level 1)**: `#FFFFFF` surface resting on a crisp hairline border (`1px solid #E2E8F0`) reinforced by an ambient, warm downward blur: `0 2px 4px -1px rgba(15, 41, 66, 0.04), 0 4px 6px -1px rgba(15, 41, 66, 0.03)`.
- **Hovered / Selected State (Level 2)**: Slightly lifted with a distinct primary accent boundary: `0 8px 16px -2px rgba(15, 41, 66, 0.08), 0 4px 8px -2px rgba(15, 41, 66, 0.04)`, combined with a `2px solid #0F2942` highlight ring.
- **Persistent Bottom Sheets & Floating Language Bar (Level 3)**: Fixed civic utility bars use `0 -4px 16px rgba(15, 41, 66, 0.10)` to visually detach from scrolling content below.

## Shapes

The shape system employs roundedness level 2 (0.5rem base radius). This produces soft, approachable geometries that dispel the visual tension of razor-sharp administrative portals without turning playful or childish.

- **Input Fields & Action Buttons**: `rounded-md` (`0.5rem` / 8px). Creates identifiable, clean touch affordances.
- **Scheme Discovery Cards & Modules**: `rounded-lg` (`1rem` / 16px). Encourages a friendly document-container feel.
- **Status Badges, Eligibility Tags & Language Switches**: Fully rounded / pill shapes (`9999px`) to immediately distinguish contextual metadata from interactive rectangular buttons and cards.

## Components

### 1. Buttons
- **Primary Action (e.g., 'Check Eligibility / पात्रता जांचें')**: Solid `#0F2942` fill, `#FFFFFF` text, `48px` minimum height, `rounded-md` (8px), horizontal padding `space-lg` (24px). Font `label-lg`.
- **Secondary Action (e.g., 'View Guidelines')**: Background `#FFFFFF`, border `2px solid #0F2942`, text `#0F2942`.
- **Assisted Audio Action**: Warm amber soft background (`#FEF3C7`), border `1px solid #F59E0B`, text `#92400E`, accompanied by an audio speaker icon to read scheme details aloud.

### 2. Scheme Status Chips & Badges
- **Eligible (पात्र)**: Fill `#ECFDF5`, text `#065F46`, border `1px solid #A7F3D0`, leading icon: checkmark circle.
- **Attention / Action Required**: Fill `#FFFBEB`, text `#92400E`, border `1px solid #FDE68A`, leading icon: alert triangle.
- **Not Eligible**: Fill `#FEF2F2`, text `#991B1B`, border `1px solid #FECACA`, leading icon: information circle.
- **Under Verification / Need More Info**: Fill `#F1F5F9`, text `#334155`, border `1px solid #CBD5E1`.

### 3. Scheme Discovery Cards
- Clean `#FFFFFF` cards with `16px` border radius and `1px solid #E2E8F0` border.
- Header contains scheme ministry/department tag in `label-sm`, scheme title in `headline-sm`, and an eligibility chip floated top-right.
- Dedicated highlight block inside the card displaying maximum benefit value in prominent format (e.g., **₹50,000** scholarship per year) with high-contrast text.
- Footer contains primary application deadline with an icon indicator and a full-width mobile tap target.

### 4. Input Fields & Form Controls
- **Inputs**: Min height `52px`, `16px` font size (preventing auto-zoom on mobile browsers), `#FFFFFF` fill, `#CBD5E1` border, `8px` corner radius. Focus state shifts border to `2px solid #0F2942` with an ambient ring.
- **Checkboxes & Radios**: Minimum `24px × 24px` physical target size embedded inside selectable list-item tiles with `16px` internal padding, giving a large, comfortable `56px` tap target for the entire row.

### 5. Multi-Language Switcher
- Fixed, prominent top-nav selector featuring vernacular scripts in native typefaces (e.g., English | हिन्दी | বাংলা | తెలుగు).
- Selected language displayed as an active pill with `#0F2942` background and `#FFFFFF` text.

### 6. Stepped Wizard Progress Indicator
- Horizontal progress track with numeric nodes (`36px × 36px` circles).
- Completed steps show `#059669` fill with a white checkmark. Active step shows `#0F2942` fill with white number and pulsing outer border. Future steps use `#F1F5F9` with `#64748B` text. Step titles sit clearly below in `label-md`.