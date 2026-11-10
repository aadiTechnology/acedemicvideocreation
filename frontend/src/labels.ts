export type CourseType = "school" | "technical";

export const COURSE_TYPES: { value: CourseType; label: string }[] = [
  { value: "school", label: "School (class, subject, chapter, topic)" },
  { value: "technical", label: "Technical course (course, track, module, lesson topic)" },
];

const LABELS = {
  school: { top: "Class", subject: "Subject", chapter: "Chapter", topic: "Topic", newTop: "New class", topPlaceholder: "Class 7" },
  technical: { top: "Course", subject: "Track", chapter: "Module", topic: "Lesson topic", newTop: "New course", topPlaceholder: "Python for Beginners" },
};

export const labelsFor = (type?: string) => LABELS[type === "technical" ? "technical" : "school"];
