from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete, and_
import logging
from datetime import datetime, timedelta

# Corrected import: Rely on models/__init__.py to provide CustomerCache
from ..models import CustomerCache
from ..models.pending_action import PendingAction
from ..models.vendor_cache import VendorCache
from ..models.account_cache import AccountCache
from ..models.conversation_history import ConversationHistory

logger = logging.getLogger(__name__)

def get_customer_by_qbo_id(db: Session, qbo_id: str) -> CustomerCache | None:
    """Fetches a customer from the cache by their QuickBooks ID."""
    logger.debug(f"Querying customer cache for QBO ID: {qbo_id}")
    statement = select(CustomerCache).where(CustomerCache.qbo_customer_id == qbo_id)
    result = db.execute(statement).scalar_one_or_none()
    if result:
        logger.debug(f"Found customer in cache by QBO ID: {result}")
    else:
        logger.debug(f"Customer with QBO ID {qbo_id} not found in cache.")
    return result

def get_customer_by_name(db: Session, name: str) -> CustomerCache | None:
    """Fetches a customer from the cache by their display name (case-insensitive)."""
    logger.debug(f"Querying customer cache for name (case-insensitive): {name}")
    # Use ilike for case-insensitive matching, though exact match might be better depending on QBO behavior
    statement = select(CustomerCache).where(CustomerCache.display_name.ilike(name))
    result = db.execute(statement).first() # Use first() in case of multiple inexact matches
    if result:
        customer = result[0]
        logger.debug(f"Found customer in cache by name: {customer}")
        return customer
    else:
        logger.debug(f"Customer with name like '{name}' not found in cache.")
        return None

def update_or_create_customer_cache(db: Session, customer_data: dict) -> CustomerCache:
    """
    Updates an existing customer cache entry or creates a new one.
    Expects customer_data to have keys like 'qbo_customer_id', 'display_name', 'email_address'.
    """
    qbo_id = customer_data.get('qbo_customer_id')
    if not qbo_id:
        raise ValueError("qbo_customer_id is required to update or create customer cache.")

    logger.info(f"Updating/creating customer cache for QBO ID: {qbo_id}")
    existing_customer = get_customer_by_qbo_id(db, qbo_id)

    if existing_customer:
        logger.debug(f"Updating existing cache entry for {qbo_id}")
        # Update existing record
        # Use setattr for cleaner updates, handling potential missing keys
        if 'display_name' in customer_data:
            existing_customer.display_name = customer_data['display_name']
        if 'email_address' in customer_data:
            existing_customer.email_address = customer_data['email_address']
        # last_synced_at should update automatically via the model's default/onupdate
        db.add(existing_customer) # Add to session to mark as dirty
        db.flush() # Persist changes
        logger.info(f"Updated customer cache for QBO ID: {qbo_id}")
        return existing_customer
    else:
        logger.debug(f"Creating new cache entry for {qbo_id}")
        # Create new record
        new_customer = CustomerCache(
            qbo_customer_id=qbo_id,
            display_name=customer_data.get('display_name'),
            email_address=customer_data.get('email_address')
        )
        if not new_customer.display_name:
             raise ValueError("display_name is required for new customer cache entry.")

        db.add(new_customer)
        db.flush() # Assigns ID and potentially triggers defaults
        # db.refresh(new_customer) # Ensure defaults like created_at/last_synced_at are loaded if needed
        logger.info(f"Created new customer cache entry for QBO ID: {qbo_id}, Name: {new_customer.display_name}")
        return new_customer

def delete_customer_cache(db: Session, qbo_id: str) -> bool:
    """Deletes a customer from the cache by QBO ID. Returns True if deleted, False otherwise."""
    logger.info(f"Attempting to delete customer cache for QBO ID: {qbo_id}")
    statement = delete(CustomerCache).where(CustomerCache.qbo_customer_id == qbo_id)
    result = db.execute(statement)
    deleted = result.rowcount > 0
    if deleted:
        logger.info(f"Deleted customer cache for QBO ID: {qbo_id}")
    else:
        logger.warning(f"Attempted to delete non-existent customer cache for QBO ID: {qbo_id}")
    return deleted

def create_pending_action(db: Session, action_id: str, details: dict, email_id: str = None, expiry_minutes: int = 60) -> PendingAction:
    """Creates a new pending action record."""
    logger.info(f"Creating pending action with ID: {action_id}")
    expires = datetime.utcnow() + timedelta(minutes=expiry_minutes)
    new_action = PendingAction(
        id=action_id,
        action_details=details,
        original_email_id=email_id,
        expires_at=expires
        # status defaults to 'PENDING'
        # created_at defaults to now()
    )
    db.add(new_action)
    db.flush() # Ensure it's persisted before returning
    logger.info(f"Pending action {action_id} created, expires at {expires}. Details: {details}")
    return new_action

def get_pending_action(db: Session, action_id: str) -> PendingAction | None:
    """Fetches a pending action by its ID."""
    logger.debug(f"Querying pending action with ID: {action_id}")
    statement = select(PendingAction).where(PendingAction.id == action_id)
    result = db.execute(statement).scalar_one_or_none()
    if result:
        logger.debug(f"Found pending action: {result}")
    else:
        logger.debug(f"Pending action with ID {action_id} not found.")
    return result

def update_pending_action_status(db: Session, action_id: str, status: str) -> PendingAction | None:
    """Updates the status of a pending action."""
    logger.info(f"Updating pending action {action_id} status to: {status}")
    action = get_pending_action(db, action_id)
    if action:
        action.status = status
        db.add(action) # Mark as dirty
        db.flush()
        logger.info(f"Pending action {action_id} status updated successfully.")
        return action
    else:
        logger.warning(f"Could not update status for non-existent pending action ID: {action_id}")
        return None

def delete_pending_action(db: Session, action_id: str) -> bool:
    """Deletes a pending action by ID. Returns True if deleted, False otherwise."""
    logger.info(f"Attempting to delete pending action with ID: {action_id}")
    statement = delete(PendingAction).where(PendingAction.id == action_id)
    result = db.execute(statement)
    deleted = result.rowcount > 0
    if deleted:
        logger.info(f"Deleted pending action with ID: {action_id}")
    else:
        logger.warning(f"Attempted to delete non-existent pending action with ID: {action_id}")
    return deleted

def prune_expired_actions(db: Session):
    """Marks pending actions whose expiry time has passed as EXPIRED."""
    now = datetime.utcnow()
    logger.info(f"Pruning expired pending actions (older than {now}).")

    # Update status of expired actions to 'EXPIRED'
    statement = update(PendingAction).where(
        and_(
            PendingAction.expires_at < now,
            PendingAction.status == 'PENDING'
        )
    ).values(status='EXPIRED')

    result = db.execute(statement)
    db.flush() # Persist the status updates
    logger.info(f"Marked {result.rowcount} pending actions as EXPIRED.")

def get_vendor_by_qbo_id(db: Session, qbo_id: str) -> VendorCache | None:
    """Fetches a vendor from the cache by QuickBooks ID."""
    logger.debug(f"Querying vendor cache for QBO ID: {qbo_id}")
    statement = select(VendorCache).where(VendorCache.qbo_vendor_id == qbo_id)
    return db.execute(statement).scalar_one_or_none()

def get_vendor_by_name(db: Session, name: str) -> VendorCache | None:
    """Fetches a vendor from the cache by display name (case-insensitive)."""
    logger.debug(f"Querying vendor cache for name (case-insensitive): {name}")
    statement = select(VendorCache).where(VendorCache.display_name.ilike(name))
    result = db.execute(statement).first()
    return result[0] if result else None

def update_or_create_vendor_cache(db: Session, vendor_data: dict) -> VendorCache:
    """
    Updates or creates a vendor cache entry.
    Expects vendor_data with 'qbo_vendor_id' and 'display_name'.
    """
    qbo_id = vendor_data.get('qbo_vendor_id')
    if not qbo_id:
        raise ValueError("qbo_vendor_id is required for vendor cache.")

    existing_vendor = get_vendor_by_qbo_id(db, qbo_id)
    if existing_vendor:
        logger.debug(f"Updating vendor cache for QBO ID: {qbo_id}")
        if 'display_name' in vendor_data:
            existing_vendor.display_name = vendor_data['display_name']
        # Add other fields if needed
        db.add(existing_vendor)
        db.flush()
        return existing_vendor
    else:
        logger.debug(f"Creating new vendor cache entry for QBO ID: {qbo_id}")
        new_vendor = VendorCache(
            qbo_vendor_id=qbo_id,
            display_name=vendor_data.get('display_name')
            # Add other fields if needed
        )
        if not new_vendor.display_name:
            raise ValueError("display_name is required for new vendor cache entry.")
        db.add(new_vendor)
        db.flush()
        return new_vendor

def get_account_by_qbo_id(db: Session, qbo_id: str) -> AccountCache | None:
    """Fetches an account from the cache by QuickBooks ID."""
    logger.debug(f"Querying account cache for QBO ID: {qbo_id}")
    statement = select(AccountCache).where(AccountCache.qbo_account_id == qbo_id)
    return db.execute(statement).scalar_one_or_none()

def get_account_by_name(db: Session, name: str) -> AccountCache | None:
    """Fetches an account from the cache by name (case-insensitive)."""
    logger.debug(f"Querying account cache for name (case-insensitive): {name}")
    statement = select(AccountCache).where(AccountCache.name.ilike(name))
    # Assuming account names are reasonably unique, but use first() just in case
    result = db.execute(statement).first()
    return result[0] if result else None

def update_or_create_account_cache(db: Session, account_data: dict) -> AccountCache:
    """
    Updates or creates an account cache entry.
    Expects account_data with 'qbo_account_id', 'name', potentially 'account_type', etc.
    """
    qbo_id = account_data.get('qbo_account_id')
    if not qbo_id:
        raise ValueError("qbo_account_id is required for account cache.")

    existing_account = get_account_by_qbo_id(db, qbo_id)
    if existing_account:
        logger.debug(f"Updating account cache for QBO ID: {qbo_id}")
        existing_account.name = account_data.get('name', existing_account.name)
        existing_account.account_type = account_data.get('account_type', existing_account.account_type)
        existing_account.account_sub_type = account_data.get('account_sub_type', existing_account.account_sub_type)
        existing_account.classification = account_data.get('classification', existing_account.classification)
        db.add(existing_account)
        db.flush()
        return existing_account
    else:
        logger.debug(f"Creating new account cache entry for QBO ID: {qbo_id}")
        new_account = AccountCache(
            qbo_account_id=qbo_id,
            name=account_data.get('name'),
            account_type=account_data.get('account_type'),
            account_sub_type=account_data.get('account_sub_type'),
            classification=account_data.get('classification')
        )
        if not new_account.name:
            raise ValueError("name is required for new account cache entry.")
        db.add(new_account)
        db.flush()
        return new_account

def bulk_update_or_create_account_cache(db: Session, accounts_data: list[dict]):
    """Efficiently updates or creates multiple account cache entries."""
    logger.info(f"Bulk updating/creating {len(accounts_data)} account cache entries.")
    # Fetch existing accounts by QBO ID for efficient update checking
    qbo_ids = [acc.get('qbo_account_id') for acc in accounts_data if acc.get('qbo_account_id')]
    existing_accounts_map = {}
    if qbo_ids:
        stmt = select(AccountCache).where(AccountCache.qbo_account_id.in_(qbo_ids))
        existing_accounts_map = {acc.qbo_account_id: acc for acc in db.execute(stmt).scalars()}
        logger.debug(f"Found {len(existing_accounts_map)} existing accounts for bulk update.")

    accounts_to_add = []
    updated_count = 0
    created_count = 0
    for account_data in accounts_data:
        qbo_id = account_data.get('qbo_account_id')
        if not qbo_id:
            logger.warning(f"Skipping account data in bulk update due to missing qbo_account_id: {account_data.get('name')}")
            continue

        existing_account = existing_accounts_map.get(qbo_id)
        if existing_account:
            # Update existing
            needs_update = False
            if existing_account.name != account_data.get('name'):
                existing_account.name = account_data.get('name')
                needs_update = True
            if existing_account.account_type != account_data.get('account_type'):
                existing_account.account_type = account_data.get('account_type')
                needs_update = True
            if existing_account.account_sub_type != account_data.get('account_sub_type'):
                existing_account.account_sub_type = account_data.get('account_sub_type')
                needs_update = True
            if existing_account.classification != account_data.get('classification'):
                existing_account.classification = account_data.get('classification')
                needs_update = True

            if needs_update:
                db.add(existing_account)
                updated_count += 1
        else:
            # Create new
            new_account = AccountCache(
                qbo_account_id=qbo_id,
                name=account_data.get('name'),
                account_type=account_data.get('account_type'),
                account_sub_type=account_data.get('account_sub_type'),
                classification=account_data.get('classification')
            )
            if not new_account.name:
                logger.warning(f"Skipping new account in bulk add due to missing name: QBO ID {qbo_id}")
                continue
            accounts_to_add.append(new_account)
            created_count += 1

    if accounts_to_add:
        db.add_all(accounts_to_add)

    if updated_count > 0 or created_count > 0:
        db.flush()
        logger.info(f"Bulk account cache update complete. Updated: {updated_count}, Created: {created_count}.")
    else:
        logger.info("No changes needed in bulk account cache update.")

# --- Conversation History CRUD --- #

def get_conversation_history(db: Session, conversation_id: str) -> list[dict]:
    """Fetches the conversation history for a given ID, ordered by sequence."""
    logger.debug(f"Querying conversation history for ID: {conversation_id}")
    statement = select(ConversationHistory).\
        where(ConversationHistory.conversation_id == conversation_id).\
        order_by(ConversationHistory.sequence)
    results = db.execute(statement).scalars().all()
    history = [turn.to_dict() for turn in results]
    logger.debug(f"Found {len(history)} turns for conversation {conversation_id}")
    return history

def save_conversation_turn(db: Session, conversation_id: str, turn_data: dict):
    """Saves a single turn to the conversation history."""
    logger.debug(f"Saving turn for conversation ID: {conversation_id}, Role: {turn_data.get('role')}")
    # Determine the next sequence number
    current_history = get_conversation_history(db, conversation_id)
    next_sequence = len(current_history)

    role = turn_data.get('role')
    content = turn_data.get('content')
    content_json = None

    if not role:
        raise ValueError("Turn data must include a 'role'.")

    # Store structured content in JSON if it's dict/list, else store in text
    if isinstance(content, (dict, list)):
        content_json = content
        content_text = None
        logger.debug("Storing turn content as JSON.")
    else:
        content_text = str(content) if content is not None else None
        logger.debug("Storing turn content as Text.")


    new_turn = ConversationHistory(
        conversation_id=conversation_id,
        sequence=next_sequence,
        role=role,
        content=content_text,
        content_json=content_json
    )
    db.add(new_turn)
    # Flush may be needed here if commit happens later
    # db.flush()
    logger.debug(f"Added turn {next_sequence} for conversation {conversation_id} to session.")
    # The commit should happen within the main loop after successful processing of the turn 