import axios from 'axios';
import { API_BASE_URL } from '../config/api';

const http = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
  timeout: 120000,
});

export default http;
