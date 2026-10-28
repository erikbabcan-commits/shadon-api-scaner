import { SCANNER_AVAILABILITY_NOTICE } from "@/lib/scanAvailability";

export function ScannerAvailabilityNotice() {
  return (
    <aside role="note" aria-label="Dostupnosť skenovacích profilov"
      className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      {SCANNER_AVAILABILITY_NOTICE}
    </aside>
  );
}
