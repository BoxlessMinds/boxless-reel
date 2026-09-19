/**
 * Admin page for managing users.
 */

import { useState } from 'react';
import { Loader2, Shield, Users, Search, Check, X, Trash2, AlertTriangle, Settings } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { EmptyState } from '@/components/ui/EmptyState';
import {
  useAdminUsers,
  useAdminUpdateUser,
  useAdminDeleteUser,
  useAdminRegistrationMode,
  useAdminUpdateRegistrationMode,
} from '@/hooks/useAdmin';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';
import type { User } from '@/api/types';

function UserRow({ user, onEdit }: { user: User; onEdit: (user: User) => void }) {
  return (
    <TableRow>
      <TableCell className="font-medium">{user.email}</TableCell>
      <TableCell>{user.display_name || '-'}</TableCell>
      <TableCell>
        <Badge variant={user.role === 'admin' ? 'default' : 'secondary'}>
          {user.role}
        </Badge>
      </TableCell>
      <TableCell>
        {user.is_active ? (
          <Badge className="bg-green-100 text-green-800">
            <Check className="mr-1 h-3 w-3" />Active
          </Badge>
        ) : (
          <Badge variant="destructive">
            <X className="mr-1 h-3 w-3" />Inactive
          </Badge>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {new Date(user.created_at).toLocaleDateString()}
      </TableCell>
      <TableCell>
        <Button variant="ghost" size="sm" onClick={() => onEdit(user)}>
          Edit
        </Button>
      </TableCell>
    </TableRow>
  );
}

export default function AdminUsersPage() {
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [editRole, setEditRole] = useState<'admin' | 'user'>('user');
  const [editIsActive, setEditIsActive] = useState(true);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { user: currentUser } = useAuth();
  const { data: usersData, isLoading } = useAdminUsers({
    search: search || undefined,
    role: roleFilter !== 'all' ? (roleFilter as 'admin' | 'user') : undefined,
    is_active: statusFilter !== 'all' ? statusFilter === 'active' : undefined,
  });
  const updateMutation = useAdminUpdateUser();
  const deleteMutation = useAdminDeleteUser();
  const { data: registrationMode, isLoading: isRegModeLoading } = useAdminRegistrationMode();
  const updateRegMode = useAdminUpdateRegistrationMode();

  const handleEdit = (user: User) => {
    setEditingUser(user);
    setEditRole(user.role as 'admin' | 'user');
    setEditIsActive(user.is_active);
  };

  const handleSave = async () => {
    if (!editingUser) return;

    try {
      await updateMutation.mutateAsync({
        userId: editingUser.id,
        data: {
          role: editRole,
          is_active: editIsActive,
        },
      });
      toast.success('User updated successfully');
      setEditingUser(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update user';
      toast.error(message);
    }
  };

  const handleDelete = async () => {
    if (!editingUser) return;

    try {
      await deleteMutation.mutateAsync(editingUser.id);
      toast.success('User deleted successfully');
      setShowDeleteConfirm(false);
      setEditingUser(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete user';
      toast.error(message);
    }
  };

  const canDeleteUser = editingUser && currentUser && editingUser.id !== currentUser.id;

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
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Shield className="h-8 w-8" />
            User Management
          </h1>
          <p className="text-muted-foreground">
            Manage users, roles, and account status.
          </p>
        </div>

        {/* Registration Settings */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Registration Settings
            </CardTitle>
            <CardDescription>
              Control how new users can register for the application.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="require-invitation">Require Invitation Code</Label>
                <p className="text-sm text-muted-foreground">
                  When enabled, users must have an invitation link to register.
                  When disabled, anyone can create an account.
                </p>
              </div>
              <Switch
                id="require-invitation"
                checked={registrationMode?.require_invitation ?? true}
                disabled={isRegModeLoading || updateRegMode.isPending}
                onCheckedChange={(checked) => {
                  updateRegMode.mutate(checked, {
                    onSuccess: () => {
                      toast.success(
                        checked
                          ? 'Registration now requires an invitation code'
                          : 'Open registration enabled'
                      );
                    },
                    onError: (error) => {
                      toast.error(
                        error instanceof Error ? error.message : 'Failed to update setting'
                      );
                    },
                  });
                }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Filters */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-5 w-5" />
              Filters
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4">
              <div className="flex-1 min-w-[200px]">
                <Label htmlFor="search" className="sr-only">Search</Label>
                <Input
                  id="search"
                  placeholder="Search by email or name..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div className="w-[150px]">
                <Select value={roleFilter} onValueChange={setRoleFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="Role" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Roles</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                    <SelectItem value="user">User</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="w-[150px]">
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Users Table */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Users
              {usersData && (
                <Badge variant="secondary" className="ml-2">
                  {usersData.total} total
                </Badge>
              )}
            </CardTitle>
            <CardDescription>
              Click on a user to edit their role or status.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!usersData?.users || usersData.users.length === 0 ? (
              <EmptyState
                icon={Users}
                title="No users found"
                description="No users match your current filters."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email</TableHead>
                    <TableHead>Display Name</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="w-[80px]">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {usersData.users.map((user) => (
                    <UserRow key={user.id} user={user} onEdit={handleEdit} />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Edit Dialog */}
      <Dialog open={!!editingUser && !showDeleteConfirm} onOpenChange={(open) => !open && setEditingUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
            <DialogDescription>
              Update user role and status for {editingUser?.email}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="role">Role</Label>
              <Select value={editRole} onValueChange={(v) => setEditRole(v as 'admin' | 'user')}>
                <SelectTrigger id="role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="user">User</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="active">Active</Label>
                <p className="text-sm text-muted-foreground">
                  Inactive users cannot log in
                </p>
              </div>
              <Switch
                id="active"
                checked={editIsActive}
                onCheckedChange={setEditIsActive}
              />
            </div>
          </div>
          <DialogFooter className="flex justify-between sm:justify-between">
            <Button
              variant="destructive"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={!canDeleteUser}
              title={!canDeleteUser ? "You cannot delete your own account" : undefined}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete User
            </Button>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setEditingUser(null)}>
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={updateMutation.isPending}>
                {updateMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  'Save Changes'
                )}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              Delete User
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to permanently delete <span className="font-medium">{editingUser?.email}</span>?
              This action cannot be undone. All data associated with this user will be removed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete User'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
