'use client';

import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { AlertCircle, Eye, EyeOff, LoaderCircleIcon } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { toAbsoluteUrl } from '@/lib/helpers';
import { safeCallbackUrl } from '@/lib/session';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { BrandMark, BrandName } from '@/components/layout/components/brand';
import { getSigninSchema, SigninSchemaType } from '../forms/signin-schema';

export function SignInForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnUrl = useMemo(() => safeCallbackUrl(searchParams.get('callbackUrl')), [searchParams]);

  const [passwordVisible, setPasswordVisible] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const form = useForm<SigninSchemaType>({
    resolver: zodResolver(getSigninSchema()),
    defaultValues: { email: '', password: '', rememberMe: false },
  });

  async function onSubmit(values: SigninSchemaType) {
    setIsProcessing(true);
    setError(null);
    try {
      const response = await fetch(toAbsoluteUrl('/api/auth/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        setError(data.detail ?? 'Connexion impossible.');
        return;
      }
      router.push(returnUrl);
      router.refresh();
    } catch {
      setError('Une erreur inattendue est survenue. Réessayez.');
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="block w-full space-y-5">
        <div className="space-y-5 pb-3">
          <div className="flex items-center justify-center gap-2 text-lg">
            <BrandMark className="h-7 text-sm px-2" />
            <BrandName />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-center">Connexion</h1>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertIcon>
              <AlertCircle />
            </AlertIcon>
            <AlertTitle>{error}</AlertTitle>
          </Alert>
        )}

        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>E-mail</FormLabel>
              <FormControl>
                <Input type="email" autoComplete="email" placeholder="vous@exemple.fr" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Mot de passe</FormLabel>
              <div className="relative">
                <Input
                  placeholder="Votre mot de passe"
                  autoComplete="current-password"
                  type={passwordVisible ? 'text' : 'password'}
                  {...field}
                />
                <Button
                  type="button"
                  variant="ghost"
                  mode="icon"
                  size="sm"
                  onClick={() => setPasswordVisible(!passwordVisible)}
                  className="absolute end-0 top-1/2 -translate-y-1/2 h-7 w-7 me-1.5 bg-transparent!"
                  aria-label={passwordVisible ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}
                >
                  {passwordVisible ? (
                    <EyeOff className="text-muted-foreground" />
                  ) : (
                    <Eye className="text-muted-foreground" />
                  )}
                </Button>
              </div>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex items-center space-x-2">
          <FormField
            control={form.control}
            name="rememberMe"
            render={({ field }) => (
              <>
                <Checkbox
                  id="remember-me"
                  checked={field.value}
                  onCheckedChange={(checked) => field.onChange(!!checked)}
                />
                <label htmlFor="remember-me" className="text-sm leading-none text-muted-foreground">
                  Rester connecté 12 heures
                </label>
              </>
            )}
          />
        </div>

        <Button type="submit" disabled={isProcessing} className="w-full">
          {isProcessing ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
          Se connecter
        </Button>

        <p className="text-sm text-muted-foreground text-center">Espace réservé au propriétaire du service.</p>
      </form>
    </Form>
  );
}
