import {
  BedDouble,
  BookOpenText,
  CalendarDays,
  ClipboardCheck,
  GraduationCap,
  HeartHandshake,
  Landmark,
  LibraryBig,
  type LucideIcon,
  PenLine,
  Phone,
  Users,
  WalletCards,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  admissions: ClipboardCheck,
  "tuition-and-fees": WalletCards,
  "academic-programmes": GraduationCap,
  "student-registration": PenLine,
  examinations: BookOpenText,
  "academic-calendar": CalendarDays,
  "library-services": LibraryBig,
  accommodation: BedDouble,
  "student-support": HeartHandshake,
  "student-affairs": Users,
  "contact-information": Phone,
  "general-information": Landmark,
};

/** Topics students ask about most come first on the welcome screen. */
const ORDER = [
  "admissions",
  "tuition-and-fees",
  "academic-programmes",
  "student-registration",
  "examinations",
  "accommodation",
  "library-services",
  "academic-calendar",
  "student-support",
  "student-affairs",
  "contact-information",
  "general-information",
];

export const topicIcon = (slug: string): LucideIcon => ICONS[slug] ?? Landmark;

export function topicRank(slug: string): number {
  const index = ORDER.indexOf(slug);
  return index === -1 ? ORDER.length : index;
}
