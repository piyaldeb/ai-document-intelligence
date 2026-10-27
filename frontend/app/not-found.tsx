import { FileSearch } from "lucide-react";
import { ButtonLink, Card, EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <Card>
      <EmptyState
        icon={<FileSearch className="size-5" aria-hidden />}
        title="Page not found"
        description="The page you are looking for does not exist or was moved."
        action={
          <ButtonLink href="/" variant="navy">
            Back to dashboard
          </ButtonLink>
        }
      />
    </Card>
  );
}
