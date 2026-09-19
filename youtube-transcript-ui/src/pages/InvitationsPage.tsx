/**
 * Invitations page for managing user invitations.
 */

import { useState } from 'react';
import { Loader2, Mail, Copy, Check, Trash2, Clock, CheckCircle2, XCircle } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { useInvitations, useCreateInvitation, useRevokeInvitation, useClearInvitation } from '@/hooks/useInvitations';
import { toast } from 'sonner';
import type { Invitation } from '@/api/types';

function getStatusBadge(status: string) {
  switch (status) {
    case 'pending':
      return <Badge variant="secondary"><Clock className="mr-1 h-3 w-3" />Pending</Badge>;
    case 'accepted':
      return <Badge className="bg-green-100 text-green-800"><CheckCircle2 className="mr-1 h-3 w-3" />Accepted</Badge>;
    case 'expired':
      return <Badge variant="outline"><Clock className="mr-1 h-3 w-3" />Expired</Badge>;
    case 'revoked':
      return <Badge variant="destructive"><XCircle className="mr-1 h-3 w-3" />Revoked</Badge>;
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}

function InvitationRow({
  invitation,
  onRevoke,
  onClear
}: {
  invitation: Invitation;
  onRevoke: (id: string) => void;
  onClear: (id: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const isPending = invitation.status === 'pending';

  const invitationUrl = `${window.location.origin}/register?token=${invitation.token}`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(invitationUrl);
      setCopied(true);
      toast.success('Invitation link copied!');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Failed to copy link');
    }
  };

  return (
    <TableRow>
      <TableCell className="font-medium">{invitation.email}</TableCell>
      <TableCell>{getStatusBadge(invitation.status)}</TableCell>
      <TableCell className="text-muted-foreground">
        {new Date(invitation.created_at).toLocaleDateString()}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {new Date(invitation.expires_at).toLocaleDateString()}
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          {isPending ? (
            <>
              <Button variant="ghost" size="icon" onClick={handleCopy} title="Copy invitation link">
                {copied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost" size="icon" title="Revoke invitation">
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Revoke Invitation</AlertDialogTitle>
                    <AlertDialogDescription>
                      Are you sure you want to revoke this invitation to {invitation.email}?
                      They will no longer be able to use this link to register.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={() => onRevoke(invitation.id)}>
                      Revoke
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </>
          ) : (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="icon" title="Clear from list">
                  <Trash2 className="h-4 w-4 text-muted-foreground" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Clear Invitation</AlertDialogTitle>
                  <AlertDialogDescription>
                    Remove this invitation to {invitation.email} from your history?
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={() => onClear(invitation.id)}>
                    Clear
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}

export default function InvitationsPage() {
  const [email, setEmail] = useState('');
  const { data: invitations, isLoading } = useInvitations();
  const createMutation = useCreateInvitation();
  const revokeMutation = useRevokeInvitation();
  const clearMutation = useClearInvitation();

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email.trim()) {
      toast.error('Please enter an email address');
      return;
    }

    try {
      const result = await createMutation.mutateAsync({ email });
      const invitationUrl = `${window.location.origin}/register?token=${result.token}`;
      await navigator.clipboard.writeText(invitationUrl);
      toast.success('Invitation created and link copied to clipboard!');
      setEmail('');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create invitation';
      toast.error(message);
    }
  };

  const handleRevoke = async (id: string) => {
    try {
      await revokeMutation.mutateAsync(id);
      toast.success('Invitation revoked');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to revoke invitation';
      toast.error(message);
    }
  };

  const handleClear = async (id: string) => {
    try {
      await clearMutation.mutateAsync(id);
      toast.success('Invitation cleared');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to clear invitation';
      toast.error(message);
    }
  };

  if (isLoading) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center py-24">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Invitations</h1>
          <p className="text-muted-foreground">
            Invite new users to the platform. They'll receive a link to create their account.
          </p>
        </div>

        {/* Create Invitation Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5" />
              Send Invitation
            </CardTitle>
            <CardDescription>
              Enter an email address to generate an invitation link.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="flex gap-4">
              <div className="flex-1">
                <Label htmlFor="email" className="sr-only">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="user@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={createMutation.isPending}
                />
              </div>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Invitation'
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Invitations List */}
        <Card>
          <CardHeader>
            <CardTitle>Your Invitations</CardTitle>
            <CardDescription>
              View and manage invitations you've sent.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!invitations?.invitations || invitations.invitations.length === 0 ? (
              <EmptyState
                icon={Mail}
                title="No invitations yet"
                description="Send your first invitation to get started."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead className="w-[100px]">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invitations.invitations.map((invitation) => (
                    <InvitationRow
                      key={invitation.id}
                      invitation={invitation}
                      onRevoke={handleRevoke}
                      onClear={handleClear}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
