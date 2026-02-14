import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface Processor {
  id: string;
  credential_id: string;
  name: string;
  version: number;
  processor_type: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  script_preview?: string;
  script_content?: string;
}

export interface ProcessorCreate {
  credential_id: string;
  name: string;
  script_content: string;
}

export interface ProcessorUpdate {
  name?: string;
  script_content?: string;
  is_active?: boolean;
}

export const processorsApi = {
  async create(
    data: ProcessorCreate,
  ): Promise<{ id: string; version: number }> {
    const response = await axios.post(`${API_URL}/processors/`, data);
    return response.data;
  },

  async listByCredential(credentialId: string): Promise<Processor[]> {
    const response = await axios.get(
      `${API_URL}/processors/credential/${credentialId}`,
    );
    return response.data;
  },

  async get(processorId: string): Promise<Processor> {
    const response = await axios.get(`${API_URL}/processors/${processorId}`);
    return response.data;
  },

  async update(
    processorId: string,
    data: ProcessorUpdate,
  ): Promise<{ id: string; version: number }> {
    const response = await axios.put(
      `${API_URL}/processors/${processorId}`,
      data,
    );
    return response.data;
  },

  async delete(processorId: string): Promise<void> {
    await axios.delete(`${API_URL}/processors/${processorId}`);
  },
};
