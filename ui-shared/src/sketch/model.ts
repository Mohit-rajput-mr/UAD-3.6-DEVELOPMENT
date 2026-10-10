// The sketch document -- the JSON engine/uad/sketch.py reads (version 1).
export interface Pt { x: number; y: number; b?: number }
export type Kind = "living" | "garage" | "carport" | "porch" | "deck" | "patio" | "balcony" | "breezeway" | "shed" | "other";
export interface Area {
  id: string; name: string; floor: string; unit: number; kind: Kind;
  gla: boolean; finished: boolean; nonstandard: boolean; subtract: boolean;
  grade?: "PartiallyBelowGrade" | "FullyBelowGrade";
  points: Pt[];
}
export interface Label { id: string; text: string; x: number; y: number }
export interface Sym { id: string; type: string; x: number; y: number; rot: number; scale: number }
export interface Door { id: string; area: string; wall: number; t: number; width: number; flip: boolean }
export interface Page {
  id: string; name: string; floorTitles: Record<string, string>;
  areas: Area[]; labels: Label[]; symbols: Sym[]; doors: Door[];
}
export interface SketchDoc { version: 1; units: "ft"; pages: Page[]; media?: Record<string, string> }

export const ABOVE = ["LevelOne", "LevelTwo", "LevelThree", "LevelFour", "LevelFive", "LevelSix", "LevelSeven", "LevelEight", "LevelNine", "LevelTen"];
export const BELOW = ["BelowGradeOne", "BelowGradeTwo", "BelowGradeThree", "BelowGradeFour", "BelowGradeFive"];
export const FLOOR_TITLE: Record<string, string> = {
  LevelOne: "First Floor", LevelTwo: "Second Floor", LevelThree: "Third Floor", LevelFour: "Fourth Floor",
  LevelFive: "Fifth Floor", LevelSix: "Sixth Floor", LevelSeven: "Seventh Floor", LevelEight: "Eighth Floor",
  LevelNine: "Ninth Floor", LevelTen: "Tenth Floor", BelowGradeOne: "Basement", BelowGradeTwo: "Lower Level 2",
  BelowGradeThree: "Lower Level 3", BelowGradeFour: "Lower Level 4", BelowGradeFive: "Lower Level 5",
};
export const NOT_LIVING: Kind[] = ["garage", "carport", "porch", "deck", "patio", "balcony", "breezeway", "shed", "other"];
export const KINDS: { value: Kind; label: string }[] = [
  { value: "living", label: "Living area" }, { value: "garage", label: "Garage" }, { value: "carport", label: "Carport" },
  { value: "porch", label: "Porch" }, { value: "deck", label: "Deck" }, { value: "patio", label: "Patio" },
  { value: "balcony", label: "Balcony" }, { value: "breezeway", label: "Breezeway" }, { value: "shed", label: "Shed" },
  { value: "other", label: "Other (not living area)" },
];

// The labels ACI Sketch offers (owner's reference 06), plus the common rest.
export const LABELS = [
  "Atrium", "Attic", "Balcony", "Bath", "Half Bath", "Bed", "Bedroom", "Boiler Room", "Bonus", "Breakfast", "Carport",
  "Closet", "Covered Patio", "Covered Porch", "Deck", "Den", "Dining", "Dining Room", "Driveway", "Elevator",
  "Enclosed Porch", "Entrance", "Exercise", "Family", "Finished", "Fireplace", "Foyer", "Front Porch", "Game Room",
  "Garage", "Great Room", "Guest House", "Gym", "Hall", "Kitchen", "Laundry", "Living", "Loft", "Mudroom", "Office",
  "Pantry", "Patio", "Porch", "Storage", "Sunroom", "Utility", "Walk-in Closet", "Washer / Dryer", "Wet Bar",
  "Workshop", "Unit 1", "Unit 2", "Unit 3", "Unit 4", "First Floor", "Second Floor", "Basement",
];

// Symbol library (owner's reference 07): each drawn as simple strokes in a
// unit box (1 = the symbol's nominal size in feet).
export interface SymbolDef { type: string; name: string; group: string; size: [number, number] }
export const SYMBOLS: SymbolDef[] = [
  { type: "refrigerator", name: "Refrigerator", group: "Appliances", size: [3, 2.5] },
  { type: "stove", name: "Stove", group: "Appliances", size: [2.5, 2.2] },
  { type: "washer", name: "Washer", group: "Appliances", size: [2.3, 2.3] },
  { type: "dryer", name: "Dryer", group: "Appliances", size: [2.3, 2.3] },
  { type: "washerdryer", name: "Combo W/D", group: "Appliances", size: [2.3, 4.6] },
  { type: "waterheater", name: "Water heater", group: "Appliances", size: [2, 2] },
  { type: "furnace", name: "Furnace", group: "Appliances", size: [2.5, 2.5] },
  { type: "freezer", name: "Freezer", group: "Appliances", size: [2.5, 2.5] },
  { type: "grill", name: "Grill", group: "Appliances", size: [3, 2] },
  { type: "tv", name: "TV", group: "Appliances", size: [4, 0.8] },
  { type: "door", name: "Door (swing)", group: "Doors & windows", size: [3, 3] },
  { type: "slider", name: "Sliding door", group: "Doors & windows", size: [6, 0.6] },
  { type: "window", name: "Window", group: "Doors & windows", size: [3, 0.5] },
  { type: "stairs", name: "Stairs", group: "Stairs & fixtures", size: [3.5, 10] },
  { type: "tub", name: "Bathtub", group: "Stairs & fixtures", size: [5, 2.5] },
  { type: "shower", name: "Shower", group: "Stairs & fixtures", size: [3, 3] },
  { type: "toilet", name: "Toilet", group: "Stairs & fixtures", size: [1.6, 2.4] },
  { type: "sink", name: "Sink", group: "Stairs & fixtures", size: [2, 1.6] },
  { type: "fireplace", name: "Fireplace", group: "Stairs & fixtures", size: [5, 2] },
];

let seq = 0;
export const uid = (p: string) => `${p}${Date.now().toString(36)}${(seq++).toString(36)}`;

export function blankPage(n: number): Page {
  return { id: uid("p"), name: `Sketch ${n}`, floorTitles: {}, areas: [], labels: [], symbols: [], doors: [] };
}
export function blankDoc(): SketchDoc { return { version: 1, units: "ft", pages: [blankPage(1)] }; }

export function newArea(points: Pt[], floor: string, unit: number, n: number): Area {
  return { id: uid("a"), name: n === 1 ? FLOOR_TITLE[floor] || "Area" : `Area ${n}`, floor, unit, kind: "living",
           gla: true, finished: true, nonstandard: false, subtract: false, points };
}

/** What a name or label says about its shape: the brief's smart detection.
 *  "Unit 2" -> unit 2; "2nd floor" -> Level 2; "basement" -> below grade;
 *  garage / porch / deck ... -> not living area. The appraiser can override. */
export function detect(text: string): Partial<Area> {
  const t = text.toLowerCase();
  const out: Partial<Area> = {};
  const u = /\bunit\s*(\d)\b/.exec(t);
  if (u) out.unit = parseInt(u[1], 10);
  if (/\b(1st|first)\s*(floor|level|fl)\b|\bmain\s*(floor|level)\b/.test(t)) out.floor = "LevelOne";
  else if (/\b(2nd|second)\s*(floor|level|fl)\b|\bupper\s*(floor|level)\b/.test(t)) out.floor = "LevelTwo";
  else if (/\b(3rd|third)\s*(floor|level|fl)\b/.test(t)) out.floor = "LevelThree";
  else if (/\b(4th|fourth)\s*(floor|level|fl)\b/.test(t)) out.floor = "LevelFour";
  else if (/\bbasement\b|\blower\s*level\b|\bcellar\b/.test(t)) out.floor = "BelowGradeOne";
  const kinds: [RegExp, Kind][] = [[/\bgarage\b/, "garage"], [/\bcarport\b/, "carport"], [/\bporch\b/, "porch"],
    [/\bdeck\b/, "deck"], [/\bpatio\b/, "patio"], [/\bbalcony\b/, "balcony"], [/\bbreezeway\b/, "breezeway"], [/\bshed\b/, "shed"]];
  for (const [re, k] of kinds) if (re.test(t)) { out.kind = k; out.gla = false; out.finished = false; break; }
  if (/\bopen\s*to\s*below\b|\batrium\b|\bopen\s*area\b/.test(t)) out.subtract = true;
  if (/\bunfinished\b/.test(t)) out.finished = false;
  return out;
}
