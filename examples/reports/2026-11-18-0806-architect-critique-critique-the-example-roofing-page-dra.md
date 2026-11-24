# Fleet Architect critique: Critique the Example Roofing page draft, a one-page site for a North Texas roofing

> **Status: needs NEXUS review.** Drafted by a local model. Not checked yet.
> Gate: **PASSED** - 0 problems.
> Run: gemma4:12b, 24s, 1 model calls, 2,873 tokens in / 804 out (local, free). Job `20261118-080549-critique-the-example-roofing-pag`.

**Brief:** Critique the Example Roofing page draft, a one-page site for a North Texas roofing contractor.

**Page:** `<workspace>\Areas\Fleet\roster\workshop\20261118-063213-build-a-premium-single-page-we\Businesses\Agency\Site_Rebuilder\sites\example-roofing-engineer\index.html`

## Summary
The page suffers from critical usability issues where the primary calls to action are physically unclickable due to a CSS overlay. The mobile layout is cramped with small navigation links, and the headline is generic rather than problem-solving.

## Top fixes
1. Give the button container position:relative and z-index:1 to make the estimate and call buttons clickable.
2. Change the headline to 'Expert Roofing Repair and Replacement in North Texas' to be more specific.
3. Increase the height of the navigation links to 44px to ensure they are easy to tap on mobile devices.

## Measured (code, not opinion)
- phone (390x844): page 3218px tall, no sideways scroll
- phone: smallest text 13.3333px
- phone: 9 of 9 links/buttons are under 40px (e.g. a "Services"; a "About"; a "Contact")
- phone: links/buttons on the first screen: Services, About, Contact, Get my complimentary estimate, Get my complimentary estimate, Call (555) 010-7771
- phone: COVERED by another layer (dimmed or unclickable): button.estimate-btn "Get my complimentary esti" under div.hero (its own container's ::before/::after overlay is painted on top: give the content position:relative and z-index:1); button.call-btn "Call (555) 010-7771" under div.hero (its own container's ::before/::after overlay is painted on top: give the content position:relative and z-index:1)
- desktop (1440x900): page 2610px tall, no sideways scroll
- desktop: smallest text 13.3333px
- desktop: 9 of 9 links/buttons are under 40px (e.g. a "Services"; a "About"; a "Contact")
- desktop: links/buttons on the first screen: Services, About, Contact, Get my complimentary estimate, Get my complimentary estimate, Call (555) 010-7771
- desktop: COVERED by another layer (dimmed or unclickable): button.estimate-btn "Get my complimentary esti" under div.hero (its own container's ::before/::after overlay is painted on top: give the content position:relative and z-index:1); button.call-btn "Call (555) 010-7771" under div.hero (its own container's ::before/::after overlay is painted on top: give the content position:relative and z-index:1)
- h1 headings: 1; images 2, 0 without alt text; viewport meta tag: yes; title: 'Example Roofing'

## Checklist

| Item | Score | Seen | Fix |
|---|---|---|---|
| first impression | 4/5 | The hero image clearly shows roofing work in progress (image 1, 2). | Add the specific service 'Roofing & Storm Repair' to the main header. |
| headline | 2/5 | The headline is 'Construction & Storm Repair' (image 1, 2). | Change the headline to 'Expert Roofing Repair and Replacement in North Texas'. |
| call to action | 1/5 | The 'Get my complimentary estimate' and 'Call' buttons are covered by a container overlay (measured facts). | Give the button container position:relative and z-index:1 to make them clickable. |
| hierarchy | 3/5 | The 'Repairs' heading is large, but the subtext is similar in weight (image 3). | Increase the font weight and size of the 'Repairs', 'Replacements', 'Renovations', and 'Custom Builds' headers. |
| readability | 3/5 | White text on a busy photo in the hero section (image 1, 2). | Add a 50% black overlay to the hero image to make the white text pop. |
| spacing | 3/5 | The navigation links 'Services', 'About', 'Contact' are very close together (image 2). | Add 15px of margin between the navigation links. |
| imagery | 5/5 | Real photos of workers on a roof and a professional headshot of the owner (image 1, 5). | None. |
| trust | 4/5 | Includes owner bio, warranty info, and contact details (image 4, 5). | Add a specific review quote from a North Texas customer. |
| mobile | 2/5 | Navigation links are under 40px, making them hard to tap on a phone (image 2). | Increase the height of the navigation links to at least 44px for easier tapping. |
| polish | 3/5 | The layout feels like a standard template with generic block styling (image 3). | Use a different background color or subtle border for the service blocks to differentiate them. |

**Screenshots:** `Areas\Fleet\roster\workshop\20261118-080549-critique-the-example-roofing-pag\desktop-first-screen.png`, `Areas\Fleet\roster\workshop\20261118-080549-critique-the-example-roofing-pag\phone-first-screen.png`, `Areas\Fleet\roster\workshop\20261118-080549-critique-the-example-roofing-pag\phone-screen-2.png`, `Areas\Fleet\roster\workshop\20261118-080549-critique-the-example-roofing-pag\phone-screen-3.png`, `Areas\Fleet\roster\workshop\20261118-080549-critique-the-example-roofing-pag\phone-screen-4.png`
