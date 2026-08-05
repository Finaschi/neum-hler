# Neumühler See — Interaktive 3D-Tiefenkarte
### UI-Design-Brief für Optimierung

Diese Datei beschreibt die aktuelle Oberfläche einer bestehenden Web-App (Three.js/WebGL,
eine einzelne HTML-Datei) mit dem Ziel, das **UI-Design zu überarbeiten/optimieren** —
nicht die 3D-Logik. Layout, Copy, Farben, Typografie und Komponentenverhalten sind
unten vollständig dokumentiert.

---

## 1. Zweck der App

Eine rekonstruierte 3D-Bathymetrie (Tiefenrelief) des Neumühler Sees (Schwerin, MV),
abgeleitet aus einer amtlichen 2D-Tiefenkonturkarte. Nutzer:innen können das Seebett frei
drehen/zoomen, auf einen Punkt tippen, um die Tiefe dort zu erfahren, und ihren eigenen
GPS-Standort relativ zur Karte anzeigen lassen. Zielgruppe: interessierte Laien, Angler,
Taucher, Wassersportler — Nutzung vor allem **auf dem Handy, oft draußen/in Sonnenlicht**.

## 2. Tech-Stack & Constraints (bitte beibehalten)

- Reines HTML + CSS + Vanilla JS, **eine Datei**, kein Build-Step.
- 3D-Rendering: Three.js r128 (`<canvas>` füllt den ganzen Viewport, `position:absolute; inset:0`).
- UI-Elemente sind **HTML/CSS-Overlays** (`position:absolute`) über dem Canvas, kein DOM-in-3D.
- Alle Layout-/Style-Änderungen sollten sich auf CSS + HTML-Struktur beschränken; die
  IDs, auf die JavaScript zugreift, **müssen erhalten bleiben** (Liste siehe Abschnitt 6).
- Muss performant auf Mobilgeräten laufen (kein schweres Blur/Filter-Overkill).
- Sprache der Oberfläche: Deutsch.

## 3. Aktuelles visuelles Konzept

- **Grundstimmung:** dunkel, "unterwasser-technisch", leicht wissenschaftlich/HUD-artig.
- **Hintergrund:** sehr dunkles Petrol/Schwarz (`#050b10`), dazu Fog im 3D-Raum für Tiefenwirkung.
- **Panels:** halbtransparente dunkle Karten (`rgba(10,22,28,0.72)`) mit `backdrop-filter: blur(14px)`,
  dünner heller Rand (`rgba(255,255,255,0.09)`), abgerundete Ecken (12px), weicher Schlagschatten.
- **Akzentfarbe:** Türkis `#2fb7c9` (Slider-Thumb, aktive Schalter, Zahlenwerte, Fokuspunkte).
- **Sekundärakzent:** warmes Gelb `#f4e98c` (aus der Tiefenlegende, für "flach/Ufer").
- **Schrift:**
  - Display/Headline: *Space Grotesk* (600), für H1 und Panel-Überschriften (Kapitälchen, letterspacing).
  - Fließtext/UI: *Inter* (400–600).
  - Zahlen/Daten: *IBM Plex Mono* (Tiefenwerte, Prozent/Meter-Angaben, Statuszeilen).
- **Farblogik der 3D-Szene selbst** (nicht UI, aber relevant für Kontrast-Entscheidungen):
  Tiefenfarbverlauf von hellem Gelb (flach) über Grün/Türkis zu Dunkelblau (tief, −17,1 m);
  Land in gedämpften Sand-/Moostönen.

## 4. Layout — aktuelle Panel-Anordnung (Desktop & Mobile)

```
┌─────────────────────────────────────────────────────────┐
│ [Titel/Kennzahlen]                      [Einstellungen] │  ← top-left / top-right
│  oben mittig: kurzer Bedienhinweis (blendet nach 3s aus) │
│                                                           │
│                     3D-SZENE (Canvas)                    │
│                                                           │
│ [Tiefenlegende]                            [Messpunkt]   │  ← bottom-left / bottom-right
└─────────────────────────────────────────────────────────┘
```

Auf schmalen Screens (≤720px) werden Panels schmaler, aber **Positionen bleiben gleich**
(4 Ecken). Das ist einer der Hauptkandidaten für Optimierung — siehe Abschnitt 7.

### 4.1 Panel: Titel (oben links, `#title`)
- H1 "Neumühler See"
- Subline: "Interaktive 3D-Tiefenkarte · rekonstruiert aus amtlicher Bathymetrie"
- Kennzahlen-Reihe (3 Werte, mono-font, türkis): **17,10 m** Max. Tiefe · **3,12 km** Länge ·
  **7,9 m** Ø Tiefe — getrennt durch dünne obere Trennlinie.

### 4.2 Panel: Einstellungen (oben rechts, `#controls`)
- Überschrift "Darstellung" (Eyebrow-Stil, klein, grau, Kapitälchen)
- Slider "Überhöhung (Tiefe)" — Wertebereich 1×–20×, Standard 8×, zeigt aktuellen Wert rechts im Label
- Toggle "Wasseroberfläche" (an/aus)
- Toggle "Auto-Rotation" (an/aus)
- Toggle "Mein Standort (GPS)" (an/aus) + Statuszeile darunter (leer / "Suche GPS-Signal…" /
  "Position gefunden · Genauigkeit ±X m" / Fehlermeldungen, farbcodiert grün/gelb/rot)
- Button-Reihe: "Draufsicht" · "Zurücksetzen"

### 4.3 Panel: Tiefenlegende (unten links, `#legend`)
- Überschrift "Wassertiefe"
- Horizontaler Farbverlaufsbalken (Gelb→Grün→Blau, 18 Stufen, aus Originalkarte übernommen)
- Skalenbeschriftung darunter: 0 m / -4 / -8 / -12 / -17,1 m
- Kleine Quellenangabe (Fußnoten-Text, 10px, gedämpfte Farbe)

### 4.4 Panel: Messpunkt (unten rechts, `#measurePanel`)
- Überschrift "Messpunkt"
- Standardzustand: Platzhaltertext "Auf die Karte tippen, um die Tiefe an diesem Punkt zu sehen."
- Nach Klick/Tap: große Zahl (22px, mono, türkis) + Label darunter, z. B. "12,4 m — Wassertiefe"
  oder in Sandfarbe "+2,1 m — Uferbereich / Land"

### 4.5 Hinweis-Pille (oben mittig, `#hint`)
- "Ziehen zum Drehen · Scrollen zum Zoomen · Rechte Maustaste zum Verschieben"
- Blendet nach ca. 3 Sekunden automatisch aus (Fade), stört danach nicht mehr.

### 4.6 Ladebildschirm (`#loading`)
- Vollbild, Spinner + Text "LADE TIEFENMODELL …", blendet nach dem ersten Frame aus.

## 5. Interaktionen, die das Design unterstützen muss

1. **Orbit-Steuerung** der 3D-Szene: Ziehen = Rotieren, Scrollen/Pinch = Zoom,
   Rechtsklick/Zwei-Finger-Pan = Verschieben. Die UI-Panels dürfen diese Gesten nicht blockieren
   (Klickfläche der Panels sollte sich auf die Panels selbst beschränken).
2. **Klick/Tap auf die 3D-Struktur** → Tiefenmessung an diesem Punkt (siehe 4.4). Muss klar
   von einer Dreh-Geste unterscheidbar sein (aktuell: Bewegungstoleranz < 5px zwischen
   Pointer-Down/Up gilt als "Klick").
3. **GPS-Live-Update**: Standortmarker (Kreis + Ring-Puls-Animation in der 3D-Szene) aktualisiert
   sich kontinuierlich; Statustext im Panel ändert sich entsprechend.
4. **Slider-Feedback**: Zahlenwert im Label aktualisiert sich live beim Ziehen.
5. Alle Toggles sind Standard-Checkbox + gestylter Pill-Switch (kein Custom-JS-Widget).

## 6. Technische Element-IDs (nicht umbenennen, nur stylen/anders anordnen)

```
#title, #controls, #legend, #measurePanel, #hint, #loading, #scene
#exagSlider, #exagVal, #waterToggle, #autoRotate, #gpsToggle, #gpsStatus
#btnTop, #btnReset, #gradientBar, #measureBody
```

## 7. Bekannte Schwachstellen / Wo Optimierung ansetzen könnte

- **Vier-Ecken-Layout** wirkt auf kleinen Handy-Screens schnell voll/eng — evtl. Panels
  einklappbar machen (z. B. Controls & Legende als ausfahrbare Sheets statt Dauerhaft-Panels).
- **Kontrast/Lesbarkeit im Freien**: Glas-Panels mit `backdrop-filter: blur` können bei hellem
  Sonnenlicht auf dem Handy schwer lesbar werden — ggf. Opazität/Kontrast für Outdoor-Nutzung erhöhen.
- **Informationsdichte** im Controls-Panel (4 Zeilen Regler/Toggles + 2 Buttons) könnte für
  Erstnutzer:innen überwältigend wirken — evtl. Progressive Disclosure (nur Wichtigstes sichtbar,
  Rest hinter "Mehr").
- **Messpunkt- und GPS-Panel** konkurrieren beide um die untere Bildschirmhälfte; evtl.
  visuelle Vereinheitlichung oder Zusammenlegung sinnvoll.
- **Corner-Only-Layout** nutzt die Bildschirmmitte gar nicht für UI — bewusst so gewählt,
  damit die 3D-Szene im Zentrum frei bleibt; das sollte als Design-Prinzip erhalten bleiben,
  wenn nicht bewusst davon abgewichen wird.
- Bisher **keine eigene Typo-Persönlichkeit über das übliche "dark tech HUD"-Muster hinaus** —
  falls ein unverwechselbareres visuelles Signature-Element gewünscht ist, wäre das ein guter
  Ansatzpunkt (z. B. eine eigene Bildsprache für die Tiefenlegende oder ein grafisches Motiv,
  das an Kartografie/Peilung erinnert).

## 8. Was NICHT verändert werden soll

- Die 3D-Szene/Logik selbst (Terrain, Wasser, Kamera, Raycasting, Geolocation-Code).
- Die deutschen Texte inhaltlich (Umformulierungen fürs Wording sind ok, Fakten nicht ändern).
- Die vier funktionalen Kernfeatures: Drehen/Zoomen, Tiefenüberhöhung, Wasseroberfläche
  ein/aus, Klick-Tiefenmessung, GPS-Standort.

---

*Kontext: Diese App wurde aus einer offiziellen PDF-Tiefenkarte (Ministerium für Landwirtschaft,
Umwelt und Verbraucherschutz M-V, Seenreferat, 1998) rekonstruiert. Max. Tiefe 17,10 m ist ein
amtlicher Wert; Länge/Ø-Tiefe stammen aus öffentlichen Quellen (Wikipedia/Wikidata).*
