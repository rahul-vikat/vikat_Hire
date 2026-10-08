import { ScreeningDetail } from "@/components/screening-detail";

type PageProps = { params: Promise<{ screeningId: string }> };

export default async function ScreeningPage({ params }: PageProps) {
  const { screeningId } = await params;
  return <ScreeningDetail screeningId={screeningId} />;
}
