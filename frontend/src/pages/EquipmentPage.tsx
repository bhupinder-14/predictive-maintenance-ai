import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Boxes, Search } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingSkeleton } from "@/components/feedback/loading-skeleton";
import { useEquipment } from "@/hooks/useEquipment";

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function EquipmentPage() {
  const equipment = useEquipment();
  const [search, setSearch] = useState("");
  const records = useMemo(() => equipment.data?.pages.flat() ?? [], [equipment.data?.pages]);
  const filtered = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    if (!term) return records;
    return records.filter((record) => [record.name, record.equipment_type, record.location ?? "", String(record.id)]
      .some((value) => value.toLocaleLowerCase().includes(term)));
  }, [records, search]);

  return (
    <div className="page-stack equipment-page">
      <PageHeader eyebrow="ASSET REGISTER" title="Equipment" description="Browse registered equipment and inspect its persisted sensor observations." />
      <Card className="equipment-directory">
        <div className="equipment-directory-toolbar">
          <div className="table-title"><div className="table-title-icon"><Boxes size={17} aria-hidden="true" /></div><div><h2>Equipment register</h2><p>Records are registered through the existing prediction workflow.</p></div></div>
          <label className="equipment-search" htmlFor="equipment-search"><Search size={15} aria-hidden="true" /><span className="sr-only">Search loaded equipment</span><input id="equipment-search" type="search" value={search} onChange={(event) => setSearch(event.currentTarget.value)} placeholder="Search loaded records" /></label>
        </div>
        <p className="equipment-coverage-note">Search covers equipment records loaded so far. The API does not provide a total count or server-side search.</p>
        {equipment.isPending ? <div className="equipment-loading" role="status" aria-label="Loading equipment"><LoadingSkeleton /><LoadingSkeleton /><LoadingSkeleton /></div>
          : equipment.isError && !equipment.data ? <ErrorState title="Equipment could not be loaded" description="The equipment endpoint did not return a valid list." onRetry={() => void equipment.refetch()} />
            : records.length === 0 ? <EmptyState title="No equipment records available" description="The backend returned an empty equipment list. No equipment is fabricated here." icon={<Boxes size={18} aria-hidden="true" />} />
              : filtered.length === 0 ? <EmptyState title="No loaded records match this search" description="Clear or change the search. Search does not query equipment records that have not been loaded." icon={<Search size={18} aria-hidden="true" />} />
                : <>
                  <div className="equipment-table-wrap">
                    <table className="equipment-table"><caption className="sr-only">Equipment records currently loaded from the backend</caption><thead><tr><th scope="col">Equipment</th><th scope="col">Type</th><th scope="col">Location</th><th scope="col">Registered</th><th scope="col"><span className="sr-only">Profile</span></th></tr></thead><tbody>
                      {filtered.map((record) => <tr key={record.id}><th scope="row"><Link className="equipment-name-link" to={`/equipment/${record.id}`}><span className="equipment-id">ID {record.id}</span><strong>{record.name}</strong></Link></th><td><span className="equipment-type-chip">{record.equipment_type}</span></td><td>{record.location ?? <span className="equipment-muted">Not recorded</span>}</td><td>{formatTimestamp(record.created_at)}</td><td><Link className="equipment-open-link" aria-label={`Open ${record.name} profile`} to={`/equipment/${record.id}`}><ArrowRight size={16} aria-hidden="true" /></Link></td></tr>)}
                    </tbody></table>
                  </div>
                  <div className="equipment-mobile-list">{filtered.map((record) => <Link className="equipment-mobile-card" key={record.id} to={`/equipment/${record.id}`}><span className="equipment-mobile-card-top"><span className="equipment-id">ID {record.id}</span><span className="equipment-type-chip">{record.equipment_type}</span></span><strong>{record.name}</strong><span>{record.location ?? "Location not recorded"}</span><small>Registered {formatTimestamp(record.created_at)}</small><ArrowRight size={16} aria-hidden="true" /></Link>)}</div>
                </>}
        {equipment.isError && equipment.data && <p className="equipment-inline-warning" role="status">Could not load the next page. Previously loaded records remain available.</p>}
        {equipment.hasNextPage && <div className="equipment-load-more"><Button type="button" variant="secondary" disabled={equipment.isFetchingNextPage} onClick={() => void equipment.fetchNextPage()}>{equipment.isFetchingNextPage ? "Loading equipment…" : "Load more equipment"}<ArrowRight size={14} aria-hidden="true" /></Button></div>}
        {records.length > 0 && <p className="equipment-loaded-count">{filtered.length} matching loaded {filtered.length === 1 ? "record" : "records"}{equipment.hasNextPage ? " · more records may be available" : " · no further page reported"}</p>}
      </Card>
    </div>
  );
}
