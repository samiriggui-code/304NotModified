import { Suspense } from 'react';
import { Metadata } from 'next';
import { SignInForm } from './sign-in-form';

export const metadata: Metadata = {
  title: 'Connexion',
};

export default function Page() {
  return (
    <Suspense>
      <SignInForm />
    </Suspense>
  );
}
