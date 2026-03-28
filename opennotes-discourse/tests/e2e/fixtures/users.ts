export interface TestUser {
  username: string;
  email: string;
  password: string;
  trustLevel: number;
}

export const ADMIN: TestUser = {
  username: "admin",
  email: "admin@opennotes.local",
  password: "opennotes-dev",
  trustLevel: 4,
};

export const REVIEWER1: TestUser = {
  username: "reviewer1",
  email: "reviewer1@test.local",
  password: "password123",
  trustLevel: 2,
};

export const REVIEWER2: TestUser = {
  username: "reviewer2",
  email: "reviewer2@test.local",
  password: "password123",
  trustLevel: 2,
};

export const NEWUSER: TestUser = {
  username: "newuser",
  email: "newuser@test.local",
  password: "password123",
  trustLevel: 0,
};

export const ALL_USERS = [ADMIN, REVIEWER1, REVIEWER2, NEWUSER];
