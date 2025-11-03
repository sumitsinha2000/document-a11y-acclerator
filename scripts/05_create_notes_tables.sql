-- ============================================
-- NOTES TABLES (with RLS)
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Notes table
CREATE TABLE IF NOT EXISTS public.notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id TEXT NOT NULL,
    title TEXT NOT NULL,
    shared BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for notes
CREATE INDEX IF NOT EXISTS idx_notes_owner_id ON public.notes(owner_id);
CREATE INDEX IF NOT EXISTS idx_notes_shared ON public.notes(shared);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON public.notes(created_at);

-- Add comments
COMMENT ON TABLE public.notes IS 'User notes with Row Level Security';
COMMENT ON COLUMN public.notes.id IS 'Primary key - UUID';
COMMENT ON COLUMN public.notes.owner_id IS 'User ID who owns this note';
COMMENT ON COLUMN public.notes.title IS 'Note title';
COMMENT ON COLUMN public.notes.shared IS 'Whether note is shared with others';

-- ============================================

-- Paragraphs table
CREATE TABLE IF NOT EXISTS public.paragraphs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    note_id UUID NOT NULL REFERENCES public.notes(id) ON DELETE CASCADE,
    content TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for paragraphs
CREATE INDEX IF NOT EXISTS idx_paragraphs_note_id ON public.paragraphs(note_id);
CREATE INDEX IF NOT EXISTS idx_paragraphs_created_at ON public.paragraphs(created_at);

-- Add comments
COMMENT ON TABLE public.paragraphs IS 'Note paragraphs with Row Level Security';
COMMENT ON COLUMN public.paragraphs.id IS 'Primary key - UUID';
COMMENT ON COLUMN public.paragraphs.note_id IS 'Foreign key to notes table';
COMMENT ON COLUMN public.paragraphs.content IS 'Paragraph content';

-- ============================================
-- Enable Row Level Security
-- ============================================

ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paragraphs ENABLE ROW LEVEL SECURITY;

-- ============================================
-- RLS Policies for Notes
-- ============================================

-- Policy: Users can insert their own notes
CREATE POLICY notes_insert_policy ON public.notes
    FOR INSERT
    WITH CHECK (owner_id = current_setting('app.current_user_id', TRUE));

-- Policy: Users can select their own notes
CREATE POLICY notes_select_own_policy ON public.notes
    FOR SELECT
    USING (owner_id = current_setting('app.current_user_id', TRUE));

-- Policy: Users can select shared notes
CREATE POLICY notes_select_shared_policy ON public.notes
    FOR SELECT
    USING (shared = TRUE);

-- Policy: Users can update their own notes
CREATE POLICY notes_update_policy ON public.notes
    FOR UPDATE
    USING (owner_id = current_setting('app.current_user_id', TRUE));

-- Policy: Users can delete their own notes
CREATE POLICY notes_delete_policy ON public.notes
    FOR DELETE
    USING (owner_id = current_setting('app.current_user_id', TRUE));

-- ============================================
-- RLS Policies for Paragraphs
-- ============================================

-- Policy: Users can insert paragraphs in their own notes
CREATE POLICY paragraphs_insert_policy ON public.paragraphs
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.notes
            WHERE notes.id = paragraphs.note_id
            AND notes.owner_id = current_setting('app.current_user_id', TRUE)
        )
    );

-- Policy: Users can select paragraphs from their own notes
CREATE POLICY paragraphs_select_own_policy ON public.paragraphs
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.notes
            WHERE notes.id = paragraphs.note_id
            AND notes.owner_id = current_setting('app.current_user_id', TRUE)
        )
    );

-- Policy: Users can select paragraphs from shared notes
CREATE POLICY paragraphs_select_shared_policy ON public.paragraphs
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.notes
            WHERE notes.id = paragraphs.note_id
            AND notes.shared = TRUE
        )
    );

-- Policy: Users can update paragraphs in their own notes
CREATE POLICY paragraphs_update_policy ON public.paragraphs
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.notes
            WHERE notes.id = paragraphs.note_id
            AND notes.owner_id = current_setting('app.current_user_id', TRUE)
        )
    );

-- Policy: Users can delete paragraphs from their own notes
CREATE POLICY paragraphs_delete_policy ON public.paragraphs
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM public.notes
            WHERE notes.id = paragraphs.note_id
            AND notes.owner_id = current_setting('app.current_user_id', TRUE)
        )
    );
