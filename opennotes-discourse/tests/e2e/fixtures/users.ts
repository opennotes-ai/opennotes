export interface TestUser {
  username: string;
  email: string;
  password: string;
  trustLevel: number;
}

export const ADMIN: TestUser = {
  username: "admin",
  email: "admin@opennotes.local",
  password: "opennotes-dev-password",
  trustLevel: 4,
};

export const REVIEWER1: TestUser = {
  username: "reviewer1",
  email: "reviewer1@test.local",
  password: "password-for-testing",
  trustLevel: 2,
};

export const REVIEWER2: TestUser = {
  username: "reviewer2",
  email: "reviewer2@test.local",
  password: "password-for-testing",
  trustLevel: 2,
};

export const NEWUSER: TestUser = {
  username: "newuser",
  email: "newuser@test.local",
  password: "password-for-testing",
  trustLevel: 0,
};

export const TL1_USER: TestUser = {
  username: "basic",
  email: "basic@test.local",
  password: "password-for-testing",
  trustLevel: 1,
};

export const TL3_USER: TestUser = {
  username: "trusted",
  email: "trusted@test.local",
  password: "password-for-testing",
  trustLevel: 3,
};

export const ALL_USERS = [ADMIN, REVIEWER1, REVIEWER2, NEWUSER, TL1_USER, TL3_USER];
