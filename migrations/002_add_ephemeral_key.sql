-- Migration: Add ephemeral_public_key column for forward secrecy
-- Run this in the Supabase SQL editor or via supabase db push.
--
-- New messages include an ephemeral X25519 public key so that the
-- sender's long-term private key is never needed by the receiver
-- to decrypt. This provides forward secrecy: even if a user's
-- passphrase is later compromised, past messages remain safe.

ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS ephemeral_public_key BYTEA;
