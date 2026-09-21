import { MessageDetailClient } from "@/components/MessageDetailClient";

export default async function MessagePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <MessageDetailClient id={id} />;
}
