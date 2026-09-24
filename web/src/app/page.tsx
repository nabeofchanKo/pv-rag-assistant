import { redirect } from "next/navigation";

// Triage is the main event — land there.
export default function Home() {
  redirect("/triage");
}
