import {pb} from "../store";
import { goto } from "$app/navigation";


export async function login(username: string, password: string) : Promise<any> {
    try {
        await pb.collection("users").authWithPassword(username, password);
    }
    catch (e) {
        console.log(e);
        return e;
    }
}

export async function signup(username: string, password: string) {
    try {
        const data = {
            username,
            password,
            passwordConfirm: password
        };
        await pb.collection("users").create(data);
        await login(username, password);
    }
    catch (e) {
        console.log(e);
        return e;
    }

}

export function logout() {
    pb.authStore.clear();

    // redirect to login page
    goto("/");

}