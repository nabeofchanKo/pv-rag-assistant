import { redirect } from "next/navigation";

// Triage is the main event — land there, in the same language.
export default async function Home({ params }: PageProps<"/[lang]">) {
  const { lang } = await params;
  redirect(`/${lang}/triage`);
}
