from domain.observation_identity import ObservationIdentity
def mint(tenant_id, capture_id, locator, digest):
    return ObservationIdentity.for_record(
        tenant_id=tenant_id, capture_id=capture_id, locator=locator, record_digest=digest
    )
