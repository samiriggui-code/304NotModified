import { z } from 'zod';

export const getSigninSchema = () => {
  return z.object({
    email: z
      .string()
      .min(1, { message: "L'email est obligatoire." })
      .email({ message: 'Adresse email invalide.' }),
    password: z.string().min(1, { message: 'Le mot de passe est obligatoire.' }),
    rememberMe: z.boolean().optional(),
  });
};

export type SigninSchemaType = z.infer<ReturnType<typeof getSigninSchema>>;
